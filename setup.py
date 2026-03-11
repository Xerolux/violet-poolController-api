from setuptools import setup, find_packages

setup(
    name="violet-poolController-api",
    version="0.0.1",
    author="Basti (Xerolux)",
    author_email="git@xerolux.de",
    description="Asynchronous Python client for the Violet Pool Controller.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/Xerolux/violet-poolController-api",
    packages=find_packages(),
    license="PolyForm Noncommercial License 1.0.0",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Home Automation",
    ],
    python_requires=">=3.12",
    install_requires=[
        "aiohttp>=3.9.0",
    ],
    project_urls={
        "Bug Tracker": "https://github.com/Xerolux/violet-poolController-api/issues",
        "License": "https://polyformproject.org/licenses/noncommercial/1.0.0/",
    },
)
