import json
from commons import settings

s = settings.read_settings()
s = settings.read_settings()
s = settings.read_settings()

print(json.dumps(s, indent=2))

print(settings.read_settings_object("", settings.AppSettings))
print()
print(settings.OpenAISettings.read())
print(settings.OpenAISettings.read().api_key)