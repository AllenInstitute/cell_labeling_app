import glob

from setuptools import setup, find_packages

requirements = [r.strip() for r in open('requirements.txt').readlines()]

setup(
      name="cell_labeling_app",
      description="Web app to label ROIs in Ophys movies",
      author="Adam Amster",
      author_email="adam.amster@alleninstitute.org",
      url="https://github.com/AllenInstitute/cell_labeling_app",
      package_dir={"": "src/server"},
      packages=find_packages(where="src/server"),
      install_requires=requirements,
      # Specify UI dependencies which need to be installed
      data_files=[('client', glob.glob('src/client/**/*', recursive=True))]
)
