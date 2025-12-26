"""Config for Shpinx."""
# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
from sphinx.ext import autodoc
from sphinx.util import logging as sphinx_logging

if not hasattr(autodoc, "logger"):
    # Sphinx 9 removed autodoc.logger; sphinx-toolbox still expects it.
    autodoc.logger = sphinx_logging.getLogger("sphinx.ext.autodoc")

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Moonraker Home Assistant"
copyright = "2023, Marc-Olivier Arsenault, Eric Tremblay"
author = "Marc-Olivier Arsenault, Eric Tremblay"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ["sphinx.ext.autosectionlabel", "sphinx_toolbox.collapse"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]
