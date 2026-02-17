from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def xml_to_string(root: Element) -> str:
    """Convert an ElementTree Element to a pretty-printed XML string."""
    rough = tostring(root, encoding='unicode')
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="    ", encoding=None)


def xml_add_attribute(parent: Element, name: str, value: str) -> Element:
    """Add an <attribute name="..." value="..." /> element."""
    return SubElement(parent, "attribute", name=name, value=value)


def xml_add_component(parent: Element, comp_type: str, comp_id: int) -> Element:
    """Add a <component type="..." id="..." /> element."""
    return SubElement(parent, "component", type=comp_type, id=str(comp_id))


def vector3_to_str(x: float, y: float, z: float) -> str:
    return f"{x:g} {y:g} {z:g}"


def vector4_to_str(x: float, y: float, z: float, w: float) -> str:
    return f"{x:g} {y:g} {z:g} {w:g}"


def quaternion_to_str(w: float, x: float, y: float, z: float) -> str:
    """Quaternion string in Urho3D format: w x y z."""
    return f"{w:g} {x:g} {y:g} {z:g}"


def write_xml_file(root: Element, filepath: str) -> None:
    """Write an XML element tree to a file with pretty formatting."""
    content = xml_to_string(root)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
