import json
import os

from typing import Any, List


class Configuration:
    def __init__(self, config_file_path):
        self.config_file_path = config_file_path
        self.config = {}
        self._default_config = {}
        if self.file_exists(config_file_path):
            with open(self.config_file_path, "r") as config_file_object:
                self.config = json.load(config_file_object)
                config_file_object.close()

    @staticmethod
    def file_exists(file_path: str):
        return os.path.exists(file_path)

    def read(self, keys: List[Any]) -> Any:
        config = self.config
        for key in keys:
            if key not in config:
                return None
            config = config[key]
        return config

    def write(self, keys: List[Any] | str, value: Any):
        if isinstance(keys, str):
            self.config[keys] = value
            return self
        for key in keys[:-1]:
            if key not in self.config:
                self.config[key] = {}
            self.config = self.config[key]
        self.config[keys[-1]] = value
        return self

    def write_dict(self, to_write: dict):
        for key, value in to_write.items():
            self.write(key, value)
        return self

    def flush(self):
        with open(self.config_file_path, "w+") as config_file_object:
            config_file_object.write(
                json.dumps(self.config, indent=2, ensure_ascii=False)
            )
            config_file_object.close()
        return self

    def set_default(self, default: dict):
        self._default_config = default
        return self

    def write_defaults(self):
        return self.write_dict(self._default_config)
