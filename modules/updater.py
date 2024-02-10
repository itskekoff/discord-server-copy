import re
import urllib.request

from packaging import version

from modules.logger import Logger


class Updater:
    def __init__(self, current_version: str):
        logger = Logger()
        logger.bind(server="UPDATER")
        resp = urllib.request.urlopen(
            url="https://raw.githubusercontent.com/itskekoff/discord-server-copy/main/main.py"
        ).read()
        target_version_string = resp.decode("utf-8")
        target_version = re.search(
            r"VERSION\s+=\s+\"([^\"]+)\"", target_version_string
        ).group(1)
        if version.parse(current_version) < version.parse(target_version):
            logger.warning("Update available. Download it from github.")
        else:
            logger.info("No updates found.")
