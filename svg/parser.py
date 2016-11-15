# SVG Path specification parser

import re
from . import path
import xml.etree.ElementTree as ET
import re

COMMANDS = set('MmZzLlHhVvCcSsQqTtAa')
UPPERCASE = set('MZLHVCSQTA')

COMMAND_RE = re.compile("([MmZzLlHhVvCcSsQqTtAa])")
FLOAT_RE = re.compile("[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")


def _tokenize_path(pathdef):
    for x in COMMAND_RE.split(pathdef):
        if x in COMMANDS:
            yield x
        for token in FLOAT_RE.findall(x):
            yield token


def parse_path(pathdef, current_pos=0j, scaler=lambda z : z):
    # In the SVG specs, initial movetos are absolute, even if
    # specified as 'm'. This is the default behavior here as well.
    # But if you pass in a current_pos variable, the initial moveto
    # will be relative to that current_pos. This is useful.
    elements = list(_tokenize_path(pathdef))
    # Reverse for easy use of .pop()
    elements.reverse()

    segments = path.Path()
    start_pos = None
    command = None

    while elements:

        if elements[-1] in COMMANDS:
            # New command.
            last_command = command  # Used by S and T
            command = elements.pop()
            absolute = command in UPPERCASE
            command = command.upper()
        else:
            # If this element starts with numbers, it is an implicit command
            # and we don't change the command. Check that it's allowed:
            if command is None:
                raise ValueError("Unallowed implicit command in %s, position %s" % (
                    pathdef, len(pathdef.split()) - len(elements)))
            last_command = command  # Used by S and T

        if command == 'M':
            # Moveto command.
            x = elements.pop()
            y = elements.pop()
            pos = float(x) + float(y) * 1j
            if absolute:
                current_pos = pos
            else:
                current_pos += pos

            # when M is called, reset start_pos
            # This behavior of Z is defined in svg spec:
            # http://www.w3.org/TR/SVG/paths.html#PathDataClosePathCommand
            start_pos = current_pos

            # Implicit moveto commands are treated as lineto commands.
            # So we set command to lineto here, in case there are
            # further implicit commands after this moveto.
            command = 'L'

        elif command == 'Z':
            # Close path
            if current_pos != start_pos:
                segments.append(path.Line(scaler(current_pos), scaler(start_pos)))
            segments.closed = True
            current_pos = start_pos
            start_pos = None
            command = None  # You can't have implicit commands after closing.

        elif command == 'L':
            x = elements.pop()
            y = elements.pop()
            pos = float(x) + float(y) * 1j
            if not absolute:
                pos += current_pos
            segments.append(path.Line(scaler(current_pos), scaler(pos)))
            current_pos = pos

        elif command == 'H':
            x = elements.pop()
            pos = float(x) + current_pos.imag * 1j
            if not absolute:
                pos += current_pos.real
            segments.append(path.Line(scaler(current_pos), scaler(pos)))
            current_pos = pos

        elif command == 'V':
            y = elements.pop()
            pos = current_pos.real + float(y) * 1j
            if not absolute:
                pos += current_pos.imag * 1j
            segments.append(path.Line(scaler(current_pos), scaler(pos)))
            current_pos = pos

        elif command == 'C':
            control1 = float(elements.pop()) + float(elements.pop()) * 1j
            control2 = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control1 += current_pos
                control2 += current_pos
                end += current_pos

            segments.append(path.CubicBezier(scaler(current_pos), scaler(control1), scaler(control2), scaler(end)))
            current_pos = end

        elif command == 'S':
            # Smooth curve. First control point is the "reflection" of
            # the second control point in the previous path.

            if last_command not in 'CS':
                # If there is no previous command or if the previous command
                # was not an C, c, S or s, assume the first control point is
                # coincident with the current point.
                control1 = current_pos
            else:
                # The first control point is assumed to be the reflection of
                # the second control point on the previous command relative
                # to the current point.
                control1 = current_pos + current_pos - segments[-1].control2

            control2 = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control2 += current_pos
                end += current_pos

            segments.append(path.CubicBezier(scaler(current_pos), scaler(control1), scaler(control2), scaler(end)))
            current_pos = end

        elif command == 'Q':
            control = float(elements.pop()) + float(elements.pop()) * 1j
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                control += current_pos
                end += current_pos

            segments.append(path.QuadraticBezier(scaler(current_pos), scaler(control), scaler(end)))
            current_pos = end

        elif command == 'T':
            # Smooth curve. Control point is the "reflection" of
            # the second control point in the previous path.

            if last_command not in 'QT':
                # If there is no previous command or if the previous command
                # was not an Q, q, T or t, assume the first control point is
                # coincident with the current point.
                control = current_pos
            else:
                # The control point is assumed to be the reflection of
                # the control point on the previous command relative
                # to the current point.
                control = current_pos + current_pos - segments[-1].control

            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                end += current_pos

            segments.append(path.QuadraticBezier(scaler(current_pos), scaler(control), scaler(end)))
            current_pos = end

        elif command == 'A':
            radius = float(elements.pop()) + float(elements.pop()) * 1j
            rotation = float(elements.pop())
            arc = float(elements.pop())
            sweep = float(elements.pop())
            end = float(elements.pop()) + float(elements.pop()) * 1j

            if not absolute:
                end += current_pos

            segments.append(path.Arc(scaler(current_pos), scaler(radius)-scaler(0j), rotation, arc, sweep, scaler(end)))
            current_pos = end

    return segments

def sizeFromString(text):
    """
    Returns size in mm, if possible.
    """
    text = re.sub(r'\s',r'', text)
    try:
        return float(text) # NOT mm
    except:
        if text[-1] == '%':
            return float(text[:-1]) # NOT mm
        units = text[-2:].lower()
        x = float(text[:-2])
        convert = { 'mm':1, 'cm':10, 'in':25.4, 'px':25.4/96, 'pt':25.4/72, 'pc':12*25.4/72 }
        try:
            return x * convert[units]
        except:
            return x # NOT mm

def getPathsFromSVG(filename):
    def getPaths(paths, scaler, tree):
        tag = re.sub(r'.*}', '', tree.tag)
        if tag == 'path':
            paths.append(parse_path(tree.attrib['d'], scaler=scaler))
        else:
            for child in tree:
                getPaths(paths, scaler, child)

    def scale(width, height, viewBox, z):
        x = (z.real - viewBox[0]) / (viewBox[2] - viewBox[0]) * width
        y = (z.imag - viewBox[1]) / (viewBox[3] - viewBox[1]) * height
        return complex(x,y)
                
    tree = ET.parse(filename)
    svg = tree.getroot()
    width = sizeFromString(svg.attrib['width'])
    height = sizeFromString(svg.attrib['height'])
    viewBox = map(float, re.split(r'[\s,]+', svg.attrib['viewBox']))
    scaler = lambda z : scale(width, height, viewBox, z)
    paths = []
    getPaths(paths, scaler, svg)
    return paths
    