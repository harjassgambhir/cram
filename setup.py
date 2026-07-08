from setuptools import setup, find_packages

setup(
    name="cram",
    version="1.0.0",
    description="CRAM-1 — Clinical Research Agent Model 1",
    packages=find_packages() + ["cram"],
    package_dir={"cram": "."},
    python_requires=">=3.11",
    install_requires=[
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "rich>=13.0.0",
    ],
    extras_require={
        "gemini": ["google-generativeai>=0.7.0"],
        "pdf":    ["markdown>=3.5.0", "weasyprint>=60.0"],
        "dev":    ["pytest>=8.0.0", "pytest-cov>=4.0.0"],
    },
    entry_points={
        "console_scripts": [
            "cram=cram.cli:main",
        ],
    },
)
