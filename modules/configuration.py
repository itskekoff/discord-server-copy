import json
import os
import typing


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

    def read(self, key: typing.Any) -> typing.Any:
        if key not in self.config:
            return None
        return self.config[key]

    def write(self, key: typing.Any, value: typing.Any):
        self.config[key] = value
        return self

    def write_dict(self, to_write: dict):
        for key, value in to_write.items():
            self.write(key, value)
        return self

    def flush(self):
        with open(self.config_file_path, "w+") as config_file_object:
            config_file_object.write(json.dumps(self.config, indent=2, ensure_ascii=False))
            config_file_object.close()
        return self

    def set_default(self, default: dict):
        self._default_config = default
        return self

    def write_defaults(self):
        return self.write_dict(self._default_config)