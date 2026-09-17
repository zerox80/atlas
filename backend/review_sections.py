"""Persisted, bounded subdivision of slow PDF sections without skipping pages."""

from review_analysis import Section


def section_key(section: Section) -> str:
    return f"{section.document}:{section.first_page}:{section.last_page}"


def expanded_sections(sections: list[Section], splits: list[str]) -> list[Section]:
    import fitz

    result = []
    for section in sections:
        if section_key(section) not in splits or section.first_page == section.last_page:
            result.append(section)
            continue
        count = section.last_page - section.first_page + 1
        middle = count // 2
        with fitz.open(stream=section.pdf, filetype="pdf") as pdf:
            children = []
            for start, end in ((0, middle - 1), (middle, count - 1)):
                with fitz.open() as part:
                    part.insert_pdf(pdf, from_page=start, to_page=end)
                    children.append(Section(section.document, section.name, section.first_page + start,
                                            section.first_page + end, part.tobytes(no_new_id=True)))
        result.extend(expanded_sections(children, splits))
    return result
