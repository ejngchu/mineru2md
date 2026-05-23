from setuptools import setup

setup(
    name="mineru2md",
    version="2.0",
    packages=["mineru2md"],
    install_requires=[
        "requests>=2.28.0",
    ],
    extras_require={
        "pymupdf": ["PyMuPDF>=1.22.0"],
    },
    entry_points={
        "console_scripts": [
            "mineru2md=mineru2md.api:main",
        ],
    },
    python_requires=">=3.8",
    description="Convert files/URLs to Markdown using MinerU APIs",
    long_description="Auto-routes between Lightweight API (free, no token) and Precision API (token required).",
    author="mineru2md",
    license="MIT",
)
