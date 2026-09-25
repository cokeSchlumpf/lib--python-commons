import hashlib
import random
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Literal


def approx_similarity(s1: str, s2: str, min_similarity: float = 0.6) -> bool:
    """
    Return True if s1 has an n-token window with similarity >= min_similarity to s2.
    - s1: longer text to search in
    - s2: phrase to look for
    - min_similarity: threshold between 0.0 and 1.0
    """

    # Normalize (lowercase + collapse spaces)
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip().lower())

    tokens1 = norm(s1).split()
    tokens2 = norm(s2).split()
    n = len(tokens2)

    if n == 0 or len(tokens1) < n:
        return False

    target = " ".join(tokens2)

    for i in range(len(tokens1) - n + 1):
        window = " ".join(tokens1[i : i + n])
        score = SequenceMatcher(None, target, window).ratio()
        if score >= min_similarity:
            return True
    return False


def clean(text: str, multiple_lines_allowed: bool = False) -> str:
    """
    Removes trailing and leading whitespaces. For single line strings, replace linebreaks with spaces.
    """

    text = text.strip()

    if not multiple_lines_allowed:
        text = text.replace("\n", " ")

    return text


def ensure_path_slugified(text: str) -> str:
    """
    Normalize each path segment into a slug format, preserving file extensions.

    Example: "/Hello World/My-File.pdf" -> "/hello-world/my-file.pdf"
    """
    if not text:
        return "/"

    # Split by slashes
    segments = text.split("/")

    # Slugify each non-empty segment
    slugified_segments = []
    for i, segment in enumerate(segments):
        if segment:  # Skip empty segments
            is_last = i == len(segments) - 1
            if is_last and "." in segment:
                # Preserve dots by slugifying each part separately
                parts = segment.split(".")
                slugified_segments.append(".".join(normalize_slug(p) for p in parts))
            else:
                slugified_segments.append(normalize_slug(segment))

    # Reconstruct path
    if not slugified_segments:
        return "/"

    return "/" + "/".join(slugified_segments)


def hash_md5(text: str) -> str:
    """
    Return MD5 hash of the text.
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def hash_sha256(text: str) -> str:
    """
    Return SHA-256 hash of the text.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_path(text: str) -> str:
    """
    Normalize a path string.

    - Collapses multiple slashes (//)
    - Ensures leading slash if not empty
    - Removes trailing slash (except for root "/")
    """
    if not text:
        return "/"

    # Collapse multiple slashes
    text = re.sub(r"/+", "/", text)

    # Ensure leading slash
    if not text.startswith("/"):
        text = "/" + text

    # Remove trailing slash (except for root)
    if len(text) > 1 and text.endswith("/"):
        text = text[:-1]

    return text


def normalize_slug(text: str) -> str:
    """
    Normalize text to slug format: lowercase alphanumeric with hyphens.

    - Removes accents and special characters
    - Converts to lowercase
    - Replaces spaces and underscores with hyphens
    - Removes consecutive hyphens
    - Strips leading/trailing hyphens
    """
    # Remove accents
    text = remove_accents(text)

    # Convert to lowercase
    text = text.lower()

    # Replace non-alphanumeric with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)

    # Remove consecutive hyphens
    text = re.sub(r"-+", "-", text)

    # Strip leading/trailing hyphens
    return text.strip("-")


def normalize_unicode(text: str, form: Literal["NFC", "NFD", "NFKC", "NFKD"] = "NFC") -> str:
    """
    Apply Unicode normalization.

    Forms:
    - NFC: Canonical Decomposition, followed by Canonical Composition
    - NFD: Canonical Decomposition
    - NFKC: Compatibility Decomposition, followed by Canonical Composition
    - NFKD: Compatibility Decomposition
    """
    return unicodedata.normalize(form, text)


def pluralize(word: str) -> str:
    """
    Pluralizes the given word.

    Parameters
    ----------
    word : str
        The word to be pluralized.

    Returns
    -------
    str
        The pluralized word.
    """

    if word.endswith("y"):
        return word[:-1] + "ies"
    elif word.endswith(("s", "sh", "ch", "x")):
        return word + "es"
    else:
        return word + "s"


def random_name(exclude_names: list[str] = [], separator: str = "-") -> str:
    """
    Creates a random name.

    This function creates docker like random slug names, e.g. jazzy-einstein.

    If `exclude_names` is provided. The function ensures that this name is not returned.
    """
    adjectives = [
        "admiring",
        "adoring",
        "affectionate",
        "agitated",
        "amazing",
        "angry",
        "awesome",
        "beautiful",
        "blissful",
        "bold",
        "boring",
        "brave",
        "busy",
        "charming",
        "clever",
        "cool",
        "compassionate",
        "competent",
        "condescending",
        "confident",
        "cranky",
        "crazy",
        "dazzling",
        "determined",
        "distracted",
        "dreamy",
        "eager",
        "ecstatic",
        "elastic",
        "elated",
        "elegant",
        "eloquent",
        "epic",
        "exciting",
        "fervent",
        "festive",
        "flamboyant",
        "focused",
        "friendly",
        "frosty",
        "funny",
        "gallant",
        "gifted",
        "goofy",
        "gracious",
        "great",
        "happy",
        "hardcore",
        "heuristic",
        "hopeful",
        "hungry",
        "infallible",
        "inspiring",
        "intelligent",
        "interesting",
        "jolly",
        "jovial",
        "keen",
        "kind",
        "laughing",
        "loving",
        "lucid",
        "magical",
        "mystifying",
        "modest",
        "musing",
        "naughty",
        "nervous",
        "nice",
        "nifty",
        "nostalgic",
        "objective",
        "optimistic",
        "peaceful",
        "pedantic",
        "pensive",
        "practical",
        "priceless",
        "quirky",
        "quizzical",
        "recursing",
        "relaxed",
        "reverent",
        "romantic",
        "sad",
        "serene",
        "sharp",
        "silly",
        "sleepy",
        "stoic",
        "strange",
        "stupefied",
        "suspicious",
        "sweet",
        "tender",
        "thirsty",
        "trusting",
        "unruffled",
        "upbeat",
        "vibrant",
        "vigilant",
        "vigorous",
        "wizardly",
        "wonderful",
        "xenodochial",
        "youthful",
        "zealous",
        "zen",
    ]

    names = [
        "albattani",
        "allen",
        "almeida",
        "archimedes",
        "ardinghelli",
        "aryabhata",
        "austin",
        "babbage",
        "banach",
        "banzai",
        "bardeen",
        "bartik",
        "bassi",
        "beaver",
        "bell",
        "benz",
        "bhabha",
        "bhaskara",
        "blackburn",
        "blackwell",
        "bohr",
        "booth",
        "borg",
        "bose",
        "boyd",
        "brahmagupta",
        "brattain",
        "brown",
        "burnell",
        "cannon",
        "carson",
        "cartwright",
        "cerf",
        "chandrasekhar",
        "chaplygin",
        "chatelet",
        "chatterjee",
        "chebyshev",
        "cohen",
        "colden",
        "cori",
        "cray",
        "curran",
        "curie",
        "darwin",
        "davinci",
        "dewdney",
        "dijkstra",
        "dubinsky",
        "easley",
        "edison",
        "einstein",
        "elbakyan",
        "elgamal",
        "elion",
        "ellis",
        "engelbart",
        "euclid",
        "euler",
        "faraday",
        "feistel",
        "fermat",
        "fermi",
        "feynman",
        "franklin",
        "gagarin",
        "galileo",
        "galois",
        "gates",
        "gauss",
        "germain",
        "goldberg",
        "goldstine",
        "goldwasser",
        "golick",
        "goodall",
        "gould",
        "greider",
        "grothendieck",
        "haibt",
        "hamilton",
        "haslett",
        "hawking",
        "hellman",
        "heisenberg",
        "hermann",
        "herschel",
        "hertz",
        "heyrovsky",
        "hodgkin",
        "hofstadter",
        "hoover",
        "hopper",
        "hugle",
        "hypatia",
        "ishizaka",
        "jackson",
        "jang",
        "jennings",
        "jepsen",
        "johnson",
        "joliot",
        "jones",
        "kalam",
        "kapitsa",
        "kare",
        "keldysh",
        "keller",
        "kepler",
        "khorana",
        "kilby",
        "kirch",
        "knuth",
        "kowalevski",
        "lalande",
        "lamarr",
        "lamport",
        "leakey",
        "leavitt",
        "lederberg",
        "lehmann",
        "lewin",
        "lichterman",
        "liskov",
        "lovelace",
        "lumiere",
        "mahavira",
        "margulis",
        "matsumoto",
        "maxwell",
        "mayer",
        "mccarthy",
        "mcclintock",
        "mclaren",
        "mclean",
        "mcnulty",
        "mendel",
        "mendeleev",
        "meitner",
        "meninsky",
        "merkle",
        "mestorf",
        "minsky",
        "mirzakhani",
        "montalcini",
        "moore",
        "morse",
        "murdock",
        "moser",
        "napier",
        "nash",
        "neumann",
        "newton",
        "nightingale",
        "nobel",
        "noether",
        "northcutt",
        "noyce",
        "panini",
        "pare",
        "pascal",
        "pasteur",
        "payne",
        "perlman",
        "pike",
        "poincare",
        "poitras",
        "proskuriakova",
        "ptolemy",
        "raman",
        "ramanujan",
        "ride",
        "ritchie",
        "rhodes",
        "robinson",
        "roentgen",
        "rosalind",
        "rubin",
        "saha",
        "sammet",
        "sanderson",
        "satoshi",
        "shamir",
        "shannon",
        "shaw",
        "shirley",
        "shockley",
        "shtern",
        "sinoussi",
        "snyder",
        "solomon",
        "spence",
        "stonebraker",
        "sutherland",
        "swanson",
        "swartz",
        "swirles",
        "taussig",
        "tesla",
        "tharp",
        "thompson",
        "torvalds",
        "tu",
        "turing",
        "varahamihira",
        "villani",
        "visvesvaraya",
        "volhard",
        "wescoff",
        "wilbur",
        "wiles",
        "williams",
        "williamson",
        "wilson",
        "wing",
        "wozniak",
        "wright",
        "wu",
        "yalow",
        "yonath",
        "zhukovsky",
    ]

    exclude_set = set(exclude_names)
    tried: set[str] = set()
    max_combinations = len(adjectives) * len(names)

    while len(tried) < max_combinations:
        adj = random.choice(adjectives)
        nm = random.choice(names)
        name = f"{adj}{separator}{nm}"

        if name in tried:
            continue
        tried.add(name)

        if name not in exclude_set:
            return name

    raise ValueError("Unable to generate a unique name. All combinations are excluded.")


def regex_replace(text: str, pattern: str, replacement: str) -> str:
    """
    Perform regex-based replacement.

    Parameters:
    - text: The input text
    - pattern: Regex pattern to match
    - replacement: Replacement string
    """
    return re.sub(pattern, replacement, text)


def remove_accents(text: str) -> str:
    """
    Remove diacritics/accents from characters.

    Example: "café" -> "cafe", "naïve" -> "naive"
    """
    # Decompose (NFD) and filter out combining characters
    nfd_form = unicodedata.normalize("NFD", text)
    return "".join(char for char in nfd_form if unicodedata.category(char) != "Mn")


def remove_symbols(text: str, allowed: str = "") -> str:
    """
    Remove symbols except those explicitly allowed.

    Parameters:
    - text: The input text
    - allowed: String of allowed symbols (e.g., "-_")
    """
    # Build pattern for allowed characters
    # Alphanumeric + whitespace + explicitly allowed symbols
    allowed_chars = set(allowed)

    result = []
    for char in text:
        if char.isalnum() or char.isspace() or char in allowed_chars:
            result.append(char)

    return "".join(result)


def to_camel_case(text: str) -> str:
    """
    Convert a string to camelCase format.

    Handles various input formats including:
    - Snake case: "document_title" -> "documentTitle"
    - Kebab case: "document-title" -> "documentTitle"
    - Space separated: "document title" -> "documentTitle"
    - PascalCase: "DocumentTitle" -> "documentTitle"
    """
    # Handle snake_case and kebab-case
    text = text.replace("_", " ").replace("-", " ")

    # Split on spaces and filter empty strings
    words = [word for word in text.split() if word]

    if not words:
        return ""

    # First word is lowercase, rest are title case
    result = words[0].lower()
    for word in words[1:]:
        result += word.capitalize()

    return result


def to_kebabcase(text: str) -> str:
    """
    Convert a string to kebab-case format.

    Handles various input formats including:
    - CamelCase/PascalCase: "DocumentTitle" -> "document-title"
    - Space separated: "Document Title" -> "document-title"
    - Snake case: "document_title" -> "document-title"
    - Mixed: "Document_Title 123" -> "document-title-123"

    Parameters
    ----------
    text : str
        The text to convert to kebab case.

    Returns
    -------
    str
        The text in kebab-case format.
    """
    # First, handle camelCase/PascalCase by inserting spaces before capitals
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)

    # Replace any non-alphanumeric characters with spaces
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)

    # Convert to lowercase and replace spaces with hyphens
    text = text.strip().lower()
    text = re.sub(r"\s+", "-", text)

    # Remove any leading/trailing hyphens
    text = text.strip("-")

    return text


def to_pascal_case(text: str) -> str:
    """
    Convert a string to PascalCase format.

    Handles various input formats including:
    - Snake case: "document_title" -> "DocumentTitle"
    - Kebab case: "document-title" -> "DocumentTitle"
    - Space separated: "document title" -> "DocumentTitle"
    - camelCase: "documentTitle" -> "DocumentTitle"
    """
    # Handle snake_case and kebab-case
    text = text.replace("_", " ").replace("-", " ")

    # Handle camelCase by inserting spaces
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)

    # Split on spaces and filter empty strings
    words = [word for word in text.split() if word]

    # Capitalize each word
    return "".join(word.capitalize() for word in words)


def to_title_case(text: str) -> str:
    """
    Convert a string to Title Case format.

    Handles various input formats including:
    - camelCase: "documentTitle" -> "Document Title"
    - kebab-case: "document-title" -> "Document Title"
    - snake_case: "document_title" -> "Document Title"
    - PascalCase: "DocumentTitle" -> "Document Title"
    """
    # Handle camelCase/PascalCase by inserting spaces before capitals
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)

    # Replace underscores and hyphens with spaces
    text = text.replace("_", " ").replace("-", " ")

    # Split, capitalize each word, and join
    words = [word for word in text.split() if word]

    return " ".join(word.capitalize() for word in words)


def to_snake_case(text: str) -> str:
    """
    Convert a string to snake_case format.

    Handles various input formats including:
    - CamelCase/PascalCase: "DocumentTitle" -> "document_title"
    - Kebab case: "document-title" -> "document_title"
    - Space separated: "Document Title" -> "document_title"
    """
    # First, handle camelCase/PascalCase by inserting spaces before capitals
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)

    # Replace any non-alphanumeric characters with spaces
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)

    # Convert to lowercase and replace spaces with underscores
    text = text.strip().lower()
    text = re.sub(r"\s+", "_", text)

    # Remove any leading/trailing underscores
    text = text.strip("_")

    return text
