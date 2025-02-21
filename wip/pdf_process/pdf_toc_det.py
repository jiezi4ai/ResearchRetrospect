# Source code attributed to pdf.toc project by Krasjet.
# Reference link: [pdf.toc](https://github.com/Krasjet/pdf.tocgen/blob/master/fitzutils/fitzutils.py)
import re
import chardet
from re import Pattern
from fitz import Document
from itertools import chain
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, List, Tuple, Iterator, Dict

DEF_TOLERANCE: float = 1e-5

@dataclass
class Point:
    x: float
    y: float

@dataclass
class ToCEntry:
    """A single entry in the table of contents"""
    level: int
    title: str
    pagenum: int
    pos: Optional[Point] = None
    # vpos == bbox.top, used for sorting
    # vpos: Optional[float] = None

    @staticmethod
    def key(e) -> Tuple[int, Point]:
        """Key used for sorting"""
        return (e.pagenum, 0 if e.pos is None else e.pos)

    def to_fitz_entry(self) -> list:
        return ([self.level, self.title, self.pagenum] +
                [self.pos] * (self.pos is not None))


def get_file_encoding(path: str) -> str:
    """Get encoding of file

    Argument
      path: file path
    Returns
      encoding string
    """
    try:
        with open(path, "rb") as f:
            enc = chardet.detect(f.read()).encoding
    except:
        enc = 'utf-8'
    return enc


# Reference link: [pdf.toc](https://github.com/Krasjet/pdf.tocgen/blob/master/pdftocgen/filter.py)
def admits_float(expect: Optional[float],
                 actual: Optional[float],
                 tolerance: float) -> bool:
    """Check if a float should be admitted by a filter"""
    return (expect is None) or \
           (actual is not None and abs(expect - actual) <= tolerance)


class FontFilter:
    """Filter on font attributes"""
    name: Pattern
    size: Optional[float]
    size_tolerance: float
    color: Optional[int]
    flags: int
    # besides the usual true (1) and false (0), we have another state,
    # unset (x), where the truth table would be
    # a b diff?
    # 0 0 0
    # 0 1 1
    # 1 0 1
    # 1 1 0
    # x 0 0
    # x 1 0
    # it's very inefficient to compare bit by bit, which would take 5 bitwise
    # operations to compare, and then 4 to combine the results, we will use a
    # trick to reduce it to 2 ops.
    # step 1: use XOR to find different bits. if unset, set bit to 0, we will
    #         take care of false positives in the next step
    # a b a^b
    # 0 0 0
    # 0 1 1
    # 1 0 1
    # 1 1 0
    # step 2: use AND with a ignore mask, (0 for ignored) to eliminate false
    #         positives
    # a b a&b
    # 0 1 0           <- no diff
    # 0 0 0           <- no diff
    # 1 1 1           <- found difference
    # 1 0 0           <- ignored
    ign_mask: int

    def __init__(self, font_dict: dict):
        self.name = re.compile(font_dict.get('name', ""))
        self.size = font_dict.get('size')
        self.size_tolerance = font_dict.get('size_tolerance', DEF_TOLERANCE)
        self.color = font_dict.get('color')
        # some branchless trick, mainly to save space
        # x * True = x
        # x * False = 0
        self.flags = (0b00001 * font_dict.get('superscript', False) |
                      0b00010 * font_dict.get('italic', False) |
                      0b00100 * font_dict.get('serif', False) |
                      0b01000 * font_dict.get('monospace', False) |
                      0b10000 * font_dict.get('bold', False))

        self.ign_mask = (0b00001 * ('superscript' in font_dict) |
                         0b00010 * ('italic' in font_dict) |
                         0b00100 * ('serif' in font_dict) |
                         0b01000 * ('monospace' in font_dict) |
                         0b10000 * ('bold' in font_dict))

    def admits(self, spn: dict) -> bool:
        """Check if the font attributes admit the span

        Argument
          spn: the span dict to be checked
        Returns
          False if the span doesn't match current font attribute
        """
        if not self.name.search(spn.get('font', "")):
            return False

        if self.color is not None and self.color != spn.get('color'):
            return False

        if not admits_float(self.size, spn.get('size'), self.size_tolerance):
            return False

        flags = spn.get('flags', ~self.flags)
        # see above for explanation
        return not (flags ^ self.flags) & self.ign_mask


class BoundingBoxFilter:
    """Filter on bounding boxes"""
    left: Optional[float]
    top: Optional[float]
    right: Optional[float]
    bottom: Optional[float]
    tolernace: float

    def __init__(self, bbox_dict: dict):
        self.left = bbox_dict.get('left')
        self.top = bbox_dict.get('top')
        self.right = bbox_dict.get('right')
        self.bottom = bbox_dict.get('bottom')
        self.tolerance = bbox_dict.get('tolerance', DEF_TOLERANCE)

    def admits(self, spn: dict) -> bool:
        """Check if the bounding box admit the span

        Argument
          spn: the span dict to be checked
        Returns
          False if the span doesn't match current bounding box setting
        """
        bbox = spn.get('bbox', (None, None, None, None))
        return (admits_float(self.left, bbox[0], self.tolerance) and
                admits_float(self.top, bbox[1], self.tolerance) and
                admits_float(self.right, bbox[2], self.tolerance) and
                admits_float(self.bottom, bbox[3], self.tolerance))
    

class ToCFilter:
    """Filter on span dictionary to pick out headings in the ToC"""
    # The level of the title, strictly > 0
    level: int
    # When set, the filter will be more *greedy* and extract all the text in a
    # block even when at least one match occurs
    greedy: bool
    font: FontFilter
    bbox: BoundingBoxFilter

    def __init__(self, fltr_dict: dict):
        lvl = fltr_dict.get('level')

        if lvl is None:
            raise ValueError("filter's 'level' is not set")
        if lvl < 1:
            raise ValueError("filter's 'level' must be >= 1")

        self.level = lvl
        self.greedy = fltr_dict.get('greedy', False)
        self.font = FontFilter(fltr_dict.get('font', {}))
        self.bbox = BoundingBoxFilter(fltr_dict.get('bbox', {}))

    def admits(self, spn: dict) -> bool:
        """Check if the filter admits the span

        Arguments
          spn: the span dict to be checked
        Returns
          False if the span doesn't match the filter
        """
        return self.font.admits(spn) and self.bbox.admits(spn)


# Reference link: [pdf.toc](https://github.com/Krasjet/pdf.tocgen/blob/master/pdftocgen/recipe.py)
def blk_to_str(blk: dict) -> str:
    """Extract all the text inside a block"""
    return " ".join([
        spn.get('text', "").strip()
        for line in blk.get('lines', [])
        for spn in line.get('spans', [])
    ])


@dataclass
class Fragment:
    """A fragment of the extracted heading"""
    text: str
    level: int


def concatFrag(frags: Iterator[Optional[Fragment]], sep: str = " ") -> Dict[int, str]:
    """Concatenate fragments to strings

    Returns
      a dictionary (level -> title) that contains the title for each level.
    """
    # accumulate a list of strings for each level of heading
    acc = defaultdict(list)
    for frag in frags:
        if frag is not None:
            acc[frag.level].append(frag.text)

    result = {}
    for level, strs in acc.items():
        result[level] = sep.join(strs)
    return result


class FoundGreedy(Exception):
    """A hacky solution to do short-circuiting in Python.

    The main reason to do this short-circuiting is to untangle the logic of
    greedy filter with normal execution, which makes the typing and code much
    cleaner, but it can also save some unecessary comparisons.

    Probably similar to call/cc in scheme or longjump in C
    c.f. https://ds26gte.github.io/tyscheme/index-Z-H-15.html#node_sec_13.2
    """
    level: int

    def __init__(self, level):
        """
        Argument
          level: level of the greedy filter
        """
        super().__init__()
        self.level = level


class Recipe:
    """The internal representation of a recipe"""
    filters: List[ToCFilter]

    def __init__(self, recipe_dict: dict):
        fltr_dicts = recipe_dict.get('heading', [])

        if len(fltr_dicts) == 0:
            raise ValueError("no filters found in recipe")
        self.filters = [ToCFilter(fltr) for fltr in fltr_dicts]

    def _extract_span(self, spn: dict) -> Optional[Fragment]:
        """Extract text from span along with level

        Argument
          spn: a span dictionary
          {
            'bbox': (float, float, float, float),
            'color': int,
            'flags': int,
            'font': str,
            'size': float,
            'text': str
          }
        Returns
          a fragment of the heading or None if no match
        """
        for fltr in self.filters:
            if fltr.admits(spn):
                text = spn.get('text', "").strip()

                if not text:
                    # don't match empty spaces
                    return None

                if fltr.greedy:
                    # propagate all the way back to extract_block
                    raise FoundGreedy(fltr.level)

                return Fragment(text, fltr.level)
        return None

    def _extract_line(self, line: dict) -> List[Optional[Fragment]]:
        """Extract matching heading fragments in a line.

        Argument
          line: a line dictionary
          {
            'bbox': (float, float, float, float),
            'wmode': int,
            'dir': (float, float),
            'spans': [dict]
          }
        Returns
          a list of fragments concatenated from result in a line
        """
        return [self._extract_span(spn) for spn in line.get('spans', [])]

    def extract_block(self, block: dict, page: int) -> List[ToCEntry]:
        """Extract matching headings in a block.

        Argument
          block: a block dictionary
          {
            'bbox': (float, float, float, float),
            'lines': [dict],
            'type': int
          }
        Returns
          a list of toc entries, concatenated from the result of lines
        """
        if block.get('type') != 0:
            # not a text block
            return []

        bbox = block.get('bbox', (0, 0, 0, 0)) # 确保 bbox 至少有四个值
        pos = Point(bbox[2], bbox[3]) # 使用 Point 结构替换 vpos 
        # vpos = block.get('bbox', (0, 0))[1]

        try:
            frags = chain.from_iterable([
                self._extract_line(ln) for ln in block.get('lines')
            ])
            titles = concatFrag(frags)

            return [
                ToCEntry(level, title, page, pos)
                for level, title in titles.items()
            ]
        except FoundGreedy as e:
            # return the entire block as a single entry
            return [ToCEntry(e.level, blk_to_str(block), page, pos)]


def extract_toc(doc: Document, recipe: Recipe) -> List[ToCEntry]:
    """Extract toc entries from a document

    Arguments
      doc: a pdf document
      recipe: recipe from user
    Returns
      a list of toc entries in the document
    """
    result = []

    for page in doc.pages():
        for blk in page.get_textpage().extractDICT().get('blocks', []):
            result.extend(
                recipe.extract_block(blk, page.number + 1)
            )

    return result


# Reference link: [pdf.toc](https://github.com/Krasjet/pdf.tocgen/blob/master/pdftocgen/tocgen.py)
def gen_toc(doc: Document, recipe_dict: dict) -> List[ToCEntry]:
    """Generate the table of content for a document from recipe

    Argument
      doc: a pdf document
      recipe_dict: the recipe dictionary used to generate the toc
    Returns
      a list of ToC entries
    """
    return extract_toc(doc, Recipe(recipe_dict))