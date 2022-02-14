from setuptools import setup, find_packages

setup(
      name="cell_labeling_app",
      use_scm_version=True,
      description=("Web app to label ROIs in Ophys movies"),
      author="Adam Amster",
      author_email="adam.amster@alleninstitute.org",
      url="https://github.com/AllenInstitute/cell_labeling_app",
      package_dir={"": "src"},
      packages=find_packages(where="src"),
      setup_requires=["setuptools_scm"]
)