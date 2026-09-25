from dataclasses import dataclass
from typing import Callable, Iterator


@dataclass
class Node[T]:
    label: str | Callable[[T], str]
    data: T
    children: list["Node[T]"]

    def _get_label(self) -> str:
        if callable(self.label):
            return self.label(self.data)
        return self.label


def create_node[T](data: T, label: str | Callable[[T], str] = str, parent: Node[T] | None = None) -> Node[T]:
    """
    Create a new tree node.

    Args:
        data: The data to store in the node
        label: Either a string label or a callable that extracts a label from the data
        parent: Optional parent node to attach this node to

    Returns:
        The newly created node
    """
    node: Node[T] = Node(label, data, [])

    if parent is not None:
        parent.children.append(node)

    return node


def render_tree[T](node: Node[T]) -> Iterator[tuple[str, str, str, T, list[T]]]:
    """
    Yields string components to render the node as a tree.

    The iterator returns a tuple with the following elements:
    * str - The indent (usually spaces/ indent when printing the item)
    * str - The prefix (e.g. `├──` or `└──`) helpful to print directory like structures
    * str - The label of the node
    * T - The actual data of this item
    * list[T] - All parent elements of the node, excluding the element itself. First element is root.
    """

    def _render(
        node: Node[T], prefix: str, is_last: bool, ancestors: list[T]
    ) -> Iterator[tuple[str, str, str, T, list[T]]]:
        # Determine connectors
        if not ancestors:  # Root node
            connector = ""
            indent = ""
        else:
            connector = "└── " if is_last else "├── "
            indent = prefix

        yield (indent, connector, node._get_label(), node.data, ancestors.copy())

        # Prepare prefix for children
        if not ancestors:
            child_prefix = ""
        else:
            child_prefix = prefix + ("    " if is_last else "│   ")

        # Recurse into children
        child_ancestors = ancestors + [node.data]
        for i, child in enumerate(node.children):
            is_last_child = i == len(node.children) - 1
            yield from _render(child, child_prefix, is_last_child, child_ancestors)

    yield from _render(node, "", True, [])


def dumps_tree[T](node: Node[T]) -> str:
    """Return tree as a string."""
    lines = [f"{indent}{prefix}{label}" for indent, prefix, label, _, _ in render_tree(node)]
    return "\n".join(lines)


def print_tree[T](node: Node[T]) -> None:
    """Print the tree."""
    print(dumps_tree(node))


def dumps_breadcrumbs[T](
    node: Node[T],
    min_depth: int = 0,
    max_depth: int | None = None,
    separator: str = " > ",
) -> str:
    """
    Return breadcrumb paths for each node in the tree as a string.

    Args:
        node: The root node of the tree
        min_depth: Minimum depth to include (0 = root). Nodes shallower than this are skipped.
        max_depth: Maximum depth to include (None = no limit). Nodes deeper than this are skipped.
        separator: The separator between path elements (default: " > ")

    Returns:
        A string with one breadcrumb path per line

    Example output:
        Financial Services
        Financial Services > Banking
        Financial Services > Banking > Retail Banking
        Financial Services > Insurance
    """

    def _breadcrumbs(node: Node[T], ancestors: list[Node[T]], depth: int) -> Iterator[str]:
        current_path = ancestors + [node]

        # Check depth constraints
        if depth >= min_depth and (max_depth is None or depth <= max_depth):
            breadcrumb = separator.join(n._get_label() for n in current_path)
            yield breadcrumb

        # Recurse into children if we haven't exceeded max_depth
        if max_depth is None or depth < max_depth:
            for child in node.children:
                yield from _breadcrumbs(child, current_path, depth + 1)

    return "\n".join(_breadcrumbs(node, [], 0))


def print_breadcrumbs[T](
    node: Node[T],
    min_depth: int = 0,
    max_depth: int | None = None,
    separator: str = " > ",
) -> None:
    """
    Print breadcrumb paths for each node in the tree.

    Args:
        node: The root node of the tree
        min_depth: Minimum depth to print (0 = root). Nodes shallower than this are skipped.
        max_depth: Maximum depth to print (None = no limit). Nodes deeper than this are skipped.
        separator: The separator between path elements (default: " > ")
    """
    print(dumps_breadcrumbs(node, min_depth, max_depth, separator))
