VERSIONS = [
    {
        "number": 16,
        "description": "Sidebar: menu links moved to sidebar, dashboard with menu actions",
        "available": True,
    },
    {
        "number": 17,
        "description": "Dashboard: widgets shown as cards in columns",
        "available": True,
    },
    {
        "number": 18,
        "description": "Form appearance: left-centered and more readable",
        "available": True,
    },
    {
        "number": 19,
        "description": "Menu appearance: more immediate and understandable",
        "available": True,
    },
    {
        "number": 20,
        "description": "User interface: cleaner and focused",
        "available": True,
    },
    {
        "number": 21,
        "description": "Clean form edit, with inline popups",
        "available": True,
    },
    {
        "number": 22,
        "description": "User interface sidebar",
        "available": True,
    },
]

LATEST_AVAILABLE_VERSION = max(v["number"] for v in VERSIONS if v["available"])
