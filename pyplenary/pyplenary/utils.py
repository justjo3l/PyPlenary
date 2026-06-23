import requests
import yaml

def readConfigYAMLFromHTML(fileURL):
    response = requests.get(fileURL, timeout=10)
    response.raise_for_status()
    return yaml.safe_load(response.text) or {}
