#!/usr/bin/env python

"""
Script to explore the standardweb3 package and StandardClient class.
"""

try:
    import inspect

    import standardweb3
    print("Successfully imported standardweb3")
    print(f"Package path: {standardweb3.__file__}")
    print(f"Package version: {getattr(standardweb3, '__version__', 'Unknown')}")
    print("\nPackage contents:")
    print(dir(standardweb3))

    # Get StandardClient details
    print("\nStandardClient details:")
    try:
        print(inspect.getfullargspec(standardweb3.StandardClient.__init__))
    except Exception as e:
        print(f"Error getting StandardClient.__init__ args: {e}")

    # Print StandardClient methods
    print("\nStandardClient methods:")
    methods = [name for name in dir(standardweb3.StandardClient) if not name.startswith('_') and name != 'address']
    for method in sorted(methods):
        print(f"- {method}")

    # Try to get address attribute
    print("\nDoes StandardClient have 'address' attribute?")
    print(hasattr(standardweb3.StandardClient, 'address'))

    # Print StandardClient doc
    print("\nStandardClient docstring:")
    print(standardweb3.StandardClient.__doc__)

except Exception as e:
    print(f"Error exploring standardweb3: {e}")
