import feedparser
import re
import os
import ssl
import shutil
import zipfile
import optparse
import urllib
from tqdm import tqdm


class DownloadProgressBar(tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


class MicrotikRss():
    def __init__(self):
        self.arch = ["arm64", "mipsbe", "smips", "tile", "arm", "mmips"]
        self.archDude = ["arm64", "tile", "arm", "mmips"]
        self.urlMain = "https://download.mikrotik.com/routeros/{version}/routeros-{arch}-{version}.npk"
        self.urlExtra = "https://download.mikrotik.com/routeros/{version}/all_packages-{arch}-{version}.zip"
        self.urlDude = "https://download.mikrotik.com/routeros/{version}/dude-{version}-{arch}.npk"
        self.versionStable = self.__latestVersion()

    def __latestVersion(self, version="current.rss"):
        NewsFeed = feedparser.parse("https://mikrotik.com/{}".format(version))
        entry = NewsFeed.entries[0]['title']
        pattern = r"RouterOS ([\d\.]+)"
        m = re.match(pattern, entry)
        return m.group(1)

    def __download(self, file, localDir):
        filename = os.path.basename(urllib.request.urlparse(file).path)
        ssl._create_default_https_context = ssl._create_unverified_context

        localFileName = os.path.join(localDir, filename)
        with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=filename) as t:
            urllib.request.urlretrieve(file, localFileName, reporthook=t.update_to)
        return localFileName

    def download(self, version, localDir):
        shutil.rmtree(localDir, ignore_errors=True)
        os.makedirs(localDir, exist_ok=True)

        for arch in self.arch:
            self.__download(self.urlMain.format(version=version, arch=arch), localDir)
            if arch in self.urlDude:
                self.urlDude(self.urlMain.format(version=version, arch=arch), localDir)
            zipFile = self.__download(self.urlExtra.format(version=version, arch=arch), localDir)
            with zipfile.ZipFile(zipFile, 'r') as zip_ref:
                print("Unzipping: {}".format(zipFile))
                zip_ref.extractall(localDir)
            os.remove(zipFile)


def isNewVersion(mtVersion, ftpServer):
    try:
        response = urllib.request.urlopen(ftpServer + "/version")
        fileVersion = response.read().decode('utf-8')
        return mtVersion != fileVersion
    except urllib.error.URLError:
        return True
    return True


if __name__ == '__main__':

    parser = optparse.OptionParser()
    parser.add_option("-f", "--ftp",
                      action="store",
                      type="string",
                      dest="ftpUrl",
                      help="Ftp server address")

    parser.add_option("-u", "--user",
                      action="store",
                      type="string",
                      dest="ftpUser",
                      help="Ftp server username")

    parser.add_option("-p", "--password",
                      action="store",
                      type="string",
                      dest="ftpPassword",
                      help="Ftp server password")

    (options, args) = parser.parse_args()

    mt = MicrotikRss()

    ftpServer = "ftp://{user}:{password}@{server}".format(user=options.ftpUser, password=options.ftpPassword, server=options.ftpUrl)

    if not isNewVersion(mt.versionStable, ftpServer):
        print("No new version found: Existing: {}".format(mt.versionStable))
        exit(0)

    mt.download(mt.versionStable, "./firmware")
