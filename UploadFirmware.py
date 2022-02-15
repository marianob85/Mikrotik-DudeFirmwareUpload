import feedparser
import re
import os
import io
import ssl
import shutil
import zipfile
import optparse
import urllib
import glob
from tqdm import tqdm
from ftplib import FTP, error_perm


class DownloadProgressBar(tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


class MicrotikRss():
    def __init__(self, localDir, ftpServer: FTP):
        self.localDir = localDir
        self.ftpServer = ftpServer
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

    def __download(self, file):
        filename = os.path.basename(urllib.request.urlparse(file).path)
        ssl._create_default_https_context = ssl._create_unverified_context

        localFileName = os.path.join(self.localDir, filename)
        with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=filename) as t:
            urllib.request.urlretrieve(file, localFileName, reporthook=t.update_to)
        return localFileName

    def download(self, version=None):
        if not version:
            version = mt.versionStable
        self.cleanup()
        os.makedirs(self.localDir, exist_ok=True)

        for arch in self.arch:
            self.__download(self.urlMain.format(version=version, arch=arch))
            if arch in self.archDude:
                self.__download(self.urlDude.format(version=version, arch=arch))
            zipFile = self.__download(self.urlExtra.format(version=version, arch=arch))
            with zipfile.ZipFile(zipFile, 'r') as zip_ref:
                print("Unzipping: {}".format(zipFile))
                zip_ref.extractall(self.localDir)
            os.remove(zipFile)

    def cleanup(self):
        shutil.rmtree(self.localDir, ignore_errors=True)

    def removeOldFiles(self):
        fileList = ftpObject.nlst()
        r = re.compile(".*\.npk")

        try:
            self.ftpServer.delete("version")
        except error_perm:
            pass
        for file in list(filter(r.match, fileList)):
            try:
                self.ftpServer.delete(file)
            except error_perm:
                pass
            print("Removed: {}".format(file))

    def isNewVersion(self, version=None):
        if not version:
            version = mt.versionStable
        try:
            r = io.BytesIO()
            self.ftpServer.retrbinary('RETR ./version', r.write)
            return r.getvalue().decode('utf-8') != version
        except error_perm:
            return True

    def uploadVersion(self, version = None ):
        if not version:
            version = mt.versionStable
        r = io.BytesIO(version.encode('utf-8'))
        self.ftpServer.storbinary("STOR version", r)

    def uploadNewFiles(self):
        self.uploadVersion()
        for file in glob.glob(os.path.join(self.localDir, "*.npk")):
            with open(file, 'rb') as infile: 
                print("Tranfering file to mikrotik: {}".format(os.path.basename(file)))
                self.ftpServer.storbinary("STOR {}".format(os.path.basename(file)), infile)


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

    ftpData = urllib.parse.urlsplit(options.ftpUrl)

    ftpObject = FTP()
    ftpObject.connect(host=ftpData.hostname)
    ftpObject.login(options.ftpUser, options.ftpPassword)
    ftpObject.cwd(ftpData.path)

    mt = MicrotikRss("./firmware", ftpObject)

    if not mt.isNewVersion():
        print("No new version found: Existing: {}".format(mt.versionStable))
        exit(0)
    print("New version found: Processing: {}".format(mt.versionStable))
    mt.download()
    mt.removeOldFiles()
    mt.uploadNewFiles()
    mt.cleanup()

    ftpObject.close()
