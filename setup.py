#!/usr/bin/env python
"""
Setup script for the job scraper package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = f.read().splitlines()

setup(
    name="job_scraper",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A tool for scraping job listings from multiple job portals",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/job-scraper",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "job_scraper=src.main:main",
        ],
    },
)