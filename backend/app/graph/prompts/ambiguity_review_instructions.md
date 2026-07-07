# AI - Requirement Review — Instructions

When reviewing a ticket's description for ambiguity, identify statements that are underspecified,
vague, or could reasonably be interpreted more than one way by an engineer implementing them.

For each ambiguity found:
- Quote or closely paraphrase the specific requirement text that is ambiguous.
- Write one specific, answerable clarifying question that would fully resolve it. A one- or
  two-sentence answer should be enough to close the ambiguity — avoid vague or open-ended questions.
- Do not flag plain scope decisions ("should we build this at all?") or missing-but-unambiguous
  details that are just not yet decided — focus only on requirements that are genuinely open to more
  than one reasonable interpretation as written.

If the description contains no genuine ambiguity, return an empty list of questions — do not invent
questions just to have something to report.
