"""依赖工具的固定契约；包来源、大小、权限不由模型指定。"""
import re

MAX_PACKAGES = 8
MAX_INSTALLS = 4
DOWNLOAD_SECONDS = 120
BUNDLE_BYTES = 24 * 1024 * 1024
EXPANDED_BYTES = 96 * 1024 * 1024
MAX_FILES = 12000
MAX_FILE_BYTES = 24 * 1024 * 1024
REGISTRY_HOSTS = frozenset({'pypi.org', 'files.pythonhosted.org', 'registry.npmjs.org'})


def validate_packages(ecosystem, packages):
    """只接受明确版本，拒绝URL、选项、路径、版本范围与重复包。"""
    if ecosystem not in {'python', 'npm'} or not isinstance(packages, list) or not 1 <= len(packages) <= MAX_PACKAGES:
        raise ValueError('选择python或npm，每次申请1到8个包')
    result, seen = [], set()
    for item in packages:
        if not isinstance(item, dict) or set(item) != {'name', 'version'}:
            raise ValueError('每个包只接受name和version')
        name, version = item['name'], item['version']
        if not isinstance(name, str) or not isinstance(version, str) or len(name) > 100 or len(version) > 50:
            raise ValueError('包名或版本无效')
        if ecosystem == 'python':
            valid_name = re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?', name)
            valid_version = re.fullmatch(r'[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc|post|dev)[0-9]+)?', version)
            key = re.sub(r'[-_.]+', '-', name).lower()
        else:
            valid_name = re.fullmatch(r'(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*', name)
            valid_version = re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?', version)
            key = name
        if not valid_name or not valid_version or key in seen:
            raise ValueError('需合法包名和明确版本，不接受URL、路径、范围或重复包')
        seen.add(key)
        result.append({'name': key, 'version': version})
    return result
