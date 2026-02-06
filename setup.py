from setuptools import setup, find_packages

setup(
    name="jarvis-do-cerrado",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "python-telegram-bot==20.8",
        "python-dotenv",
        "pyyaml",
        "psutil",
        "speedtest-cli",
        "wakeonlan",
        "mac-vendor-lookup",
        "scapy",
        "bleak",
        "google-generativeai",
        "tinytuya"
    ],
)
