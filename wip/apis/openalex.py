# openalex refer to https://docs.openalex.org/how-to-use-the-api/get-single-entities
# openalex showing less capable compared to semantic scholar, could serve as additoinal source of paper metadata
# https://github.com/J535D165/pyalex
from pyalex import Works, Authors, Sources, Institutions, Topics, Publishers, Funders

import pyalex

pyalex.config.email = "ai4fun2004@gmail.com"

# same as
Works()["https://doi.org/10.48550/arXiv.2501.04682"]