from setuptools import setup

setup(
    name="flowlog",
    version="1.0.0",
    description="A modern CLI project tracker with AI insights",
    py_modules=["main"],
    package_dir={"": "E:/programming and stuff/cli project tracker"},
    install_requires=[
        "typer",
        "rich",
        "pyfiglet",
        "python-dotenv",
        "requests",
        "google-generativeai",
    ],
    entry_points={
        "console_scripts": [
            "flowlog=main:app",
        ],
    },
    python_requires=">=3.8",
)