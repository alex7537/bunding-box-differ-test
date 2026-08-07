import yaml


class LoadConfig(object):
    def load_models(self):
        with open('config/models.yaml', 'r', encoding='utf-8') as file:
            models_data = yaml.safe_load(file)
            # print(models_data)
            return models_data

    def load_model_config(self, model_name):
        models_data = self.load_models()

        for model in models_data.get('models', []):
            if model.get('model_name') == model_name:
                if model.get('config_file'):
                    config_file_path = model.get('config_file')
                    with open(config_file_path, 'r') as config_file:
                        config_data = yaml.safe_load(config_file)
                        # print("config_data")
                        return config_data

    # def get_paths(self):
    #     models_data = self.load_models()
    #     print('bb', models_data)
    #     a = models_data.get("paths")
    #     print("12", a)

    def get_paths(self, path_name=None):
        models_data = self.load_models()
        paths = []

        if 'models' in models_data:
            for path in models_data['paths']:
                if 'path_name' in path and path['path_name'] == path_name:
                    paths.append(path.get('path', ''))

        return ', '.join(paths)

    def get_is_output_json(self):
        result = True
        try:
            models_data = self.load_models()
            if models_data.get("output_json") == "False":
                result = False
        except Exception as e:
            return True

        return result