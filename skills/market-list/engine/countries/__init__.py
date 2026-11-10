"""Country modules. A country with its own module gets a registry sweep, money data and board members.
Every other European country uses `generic`: discovery through web search, directories and Clay."""
import importlib

def load(code):
    code = code.lower()
    try:
        return importlib.import_module(f"countries.{code}")
    except ModuleNotFoundError:
        mod = importlib.import_module("countries.generic")
        mod.INFO = dict(mod.INFO, code=code.upper())
        return mod
