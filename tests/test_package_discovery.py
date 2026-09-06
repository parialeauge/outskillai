import importlib


def test_package_names_are_importable():
    modules = [
        "apps.api",
        "backend.rag_engine",
        "backend.agent_builder",
        "shared",
    ]

    for module_name in modules:
        module = importlib.import_module(module_name)
        assert module.__name__ == module_name
