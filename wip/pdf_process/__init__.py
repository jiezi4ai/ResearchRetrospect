# __init__.py
# frequently used names for paper titles
SECTION_TITLES = ["Abstract",
                'Introduction', 'Related Work', 'Background',
                "Introduction and Motivation", "Computation Function", " Routing Function",
                "Preliminary", "Problem Formulation",
                'Methods', 'Methodology', "Method", 'Approach', 'Approaches',
                "Materials and Methods", "Experiment Settings",
                'Experiment', "Experimental Results", "Evaluation", "Experiments",
                "Results", 'Findings', 'Data Analysis',
                "Discussion", "Results and Discussion", "Conclusion",
                'References',
                "Acknowledgments", "Appendix", "FAQ", "Frequently Asked Questions"]
APPENDDIX_TITLES = ["Reference", "Acknowledgment", "Appendix", "FAQ", "Frequently Asked Question"]     

# name patterns for image / table / equation names
IMG_REGX_NAME_PTRN = r"(pic|picture|img|image|chart|figure|fig|table|tbl)\s*([0-9]+(?:\.[0-9]+)?|[0-9]+|[IVXLCDM]+|[a-zA-Z]+)"
TBL_REGX_NAME_PTRN = r"(tbl|table|chart|figure|fig)\s*([0-9]+(?:\.[0-9]+)?|[0-9]+|[IVXLCDM]+|[a-zA-Z]+)"
EQT_REGX_NAME_PTRN = r"(formula|equation|notation|syntax)\s*([0-9]+(?:\.[0-9]+)?|[0-9]+|[IVXLCDM]+|[a-zA-Z]+)"