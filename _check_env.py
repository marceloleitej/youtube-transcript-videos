import sys
print("Python:", sys.executable)
print("Path:", sys.prefix)
try:
    import PySide6
    print("PySide6 OK:", PySide6.__version__)
except ImportError as e:
    print("PySide6 MISSING:", e)
