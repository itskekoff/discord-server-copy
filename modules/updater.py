import requests
import re
from packaging import version
import logging

from modules.logger import Logger


class Updater:
    def __init__(self, current_version: str, github_repo: str):
        """
        Initializes the Updater class with the current version and the GitHub repository.

        Args:
            current_version (str): The current version of the application.
            github_repo (str): The GitHub repository where the source is located.
        """
        self.current_version = current_version
        self.github_repo = github_repo
        self.logger = Logger(debug_enabled=True)
        self.logger.bind(source="Updater")

    def get_latest_version(self):
        """
         Retrieves the latest version of the application from the main.py file
         in the given GitHub repository.

         Returns:
             str: The latest version as a string if found, None otherwise.
         """
        try:
            url = f"https://raw.githubusercontent.com/{self.github_repo}/main/main.py"
            response = requests.get(url)
            response.raise_for_status()

            target_version_match = re.search(r"VERSION\s*=\s*['\"]([^'\"]+)['\"]", response.text)
            if target_version_match:
                return target_version_match.group(1)
        except requests.RequestException as e:
            self.logger.error(f"Error checking for updates: {e}")
            return None

    def check_for_updates(self):
        """
        Checks if the application is up-to-date by comparing the current version
        with the latest version available on the GitHub repository.

        If a new version is available, a warning is logged with the current and
        latest version. If the application is up-to-date or an error occurs,
        the corresponding information is logged.
        """
        latest_version = self.get_latest_version()
        if latest_version and version.parse(self.current_version) < version.parse(latest_version):
            self.logger.warning(f"Update available. Download it from GitHub.")
            self.logger.warning(f"Current version is {self.current_version}, latest version: {latest_version}")
        elif latest_version:
            self.logger.info("No updates found.")
        else:
            self.logger.error("Unable to check for updates")
