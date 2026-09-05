import importlib


def test_package_names_are_importable():
    modules = [
        "apps.api",
        "packages.rag_engine",
        "packages.agent_builder",
        "shared",
    ]

    for module_name in modules:
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name
