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
    def __init__(self, localDir, version):
        self.localDir = localDir
        self.arch = ["arm64", "mipsbe", "smips", "tile", "arm", "mmips"]
        self.archDude = ["arm64", "tile", "arm", "mmips"]
        self.urlMain = ["https://download.mikrotik.com/routeros/{version}/routeros-{arch}-{version}.npk",
                        "https://download.mikrotik.com/routeros/{version}/routeros-{version}-{arch}.npk"]
        self.urlExtra = ["https://download.mikrotik.com/routeros/{version}/all_packages-{arch}-{version}.zip",
                         "https://download.mikrotik.com/routeros/{version}/all_packages-{version}-{arch}.zip"]
        self.urlDude = "https://download.mikrotik.com/routeros/{version}/dude-{version}-{arch}.npk"
        if version and version != "None":
            self.versionStable = version
        else:
            self.versionStable = self._latestVersion()

    def _latestVersion(self, version="current.rss"):
        NewsFeed = feedparser.parse("https://mikrotik.com/{}".format(version))
        entry = NewsFeed.entries[0]['title']
        pattern = r"RouterOS ([\d\.]+)"
        m = re.match(pattern, entry)
        return m.group(1)

    def _isRouterOS(self, versionShort):
        return self.versionStable.startswith(str(versionShort))

    def _download(self, file):
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
            found = False
            for url in self.urlMain:
                if not found:
                    try:
                        self._download(url.format(version=version, arch=arch))
                        found = True
                    except urllib.error.HTTPError:
                        pass

            if not found:
                exit(1)
            if self._isRouterOS(6):
                if arch in self.archDude:
                    self._download(self.urlDude.format(version=version, arch=arch))

            zipFile = None
            for url in self.urlExtra:
                if zipFile is None:
                    try:
                        zipFile = self._download(url.format(version=version, arch=arch))
                    except urllib.error.HTTPError:
                        pass
            if not zipFile:
                exit(1)
            with zipfile.ZipFile(zipFile, 'r') as zip_ref:
                print("Unzipping: {}".format(zipFile))
                zip_ref.extractall(self.localDir)
            os.remove(zipFile)

    def cleanup(self):
        shutil.rmtree(self.localDir, ignore_errors=True)

    def removeOldFiles(self, ftpServer: FTP):
        fileList = ftpObject.nlst()
        r = re.compile(".*\.npk")

        try:
            ftpServer.delete("version")
        except error_perm:
            pass
        for file in list(filter(r.match, fileList)):
            try:
                ftpServer.delete(file)
            except error_perm:
                pass
            print("Removed: {}".format(file))

    def isNewVersion(self, ftpServer: FTP, version=None):
        if not version:
            version = mt.versionStable
        try:
            r = io.BytesIO()
            ftpServer.retrbinary('RETR ./version', r.write)
            return r.getvalue().decode('utf-8') != version
        except error_perm:
            return True

    def uploadVersion(self, ftpServer: FTP, version=None):
        if not version:
            version = mt.versionStable
        r = io.BytesIO(version.encode('utf-8'))
        ftpServer.storbinary("STOR version", r)

    def uploadNewFiles(self, ftpServer: FTP):
        self.uploadVersion(ftpServer)
        for file in glob.glob(os.path.join(self.localDir, "*.npk")):
            with open(file, 'rb') as infile:
                print("Tranfering file to mikrotik: {}".format(os.path.basename(file)))
                ftpServer.storbinary("STOR {}".format(os.path.basename(file)), infile)


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
    parser.add_option("-v", "--version",
                      action="store",
                      type="string",
                      dest="version",
                      default=None,
                      help="RoS Version")

    (options, args) = parser.parse_args()

    ftpObject = None

    mt = MicrotikRss("./firmware", options.version)

    if options.ftpUrl:
        ftpData = urllib.parse.urlsplit(options.ftpUrl)
        ftpObject = FTP()
        ftpObject.connect(host=ftpData.hostname)
        ftpObject.login(options.ftpUser, options.ftpPassword)
        ftpObject.cwd(ftpData.path)

        if not mt.isNewVersion(ftpObject):
            print("No new version found: Existing: {}".format(mt.versionStable))
            exit(0)

    print("New version found: Processing: {}".format(mt.versionStable))
    mt.download()

    if ftpObject:
        mt.removeOldFiles(ftpObject)
        mt.uploadNewFiles(ftpObject)

        ftpObject.close()
        mt.cleanup()
