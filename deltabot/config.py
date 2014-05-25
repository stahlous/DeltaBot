import json
import os


class Config(object):
    """
    This object holds the configuration options for the bot,
    except that the first layer of keys are attributes, not dict keys
    """

    def __init__(self, config_file):
        if isinstance(config_file, dict):
            self.attrs = config_file
        elif os.path.isfile(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                self.attrs = json.load(f)
        else:
            self.attrs = json.loads(config_file)

    def __getattr__(self, name):
        return self.attrs.get(name)

    def __getitem__(self, name):
        return self.attrs.get(name)
