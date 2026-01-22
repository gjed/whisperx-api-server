from collections import OrderedDict

from fastapi.responses import JSONResponse, Response
from whisperx.utils import WriteAudacity, WriteSRT, WriteVTT

from whisperx_api_server.config import MediaType


def _get_segments(transcript: dict) -> list[dict]:
    """Extract segments list from transcript, handling both formats."""
    segments = transcript.get("segments", {})
    if isinstance(segments, dict):
        return segments.get("segments", [])
    return segments


def _format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_md_basic(transcript: dict, include_timestamps: bool = False) -> str:
    """
    Format transcript as simple markdown paragraphs.

    Output:
        Speaker Name: What they said.

        Another Speaker: Their response.
    """
    segments = _get_segments(transcript)
    lines = []

    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        text = segment.get("text", "").strip()
        if not text:
            continue

        if include_timestamps:
            timestamp = _format_timestamp(segment.get("start", 0))
            lines.append(f"{speaker} [{timestamp}]: {text}")
        else:
            lines.append(f"{speaker}: {text}")
        lines.append("")  # Empty line between messages

    return "\n".join(lines).strip()


def format_md_list(transcript: dict, include_timestamps: bool = False) -> str:
    """
    Format transcript as a markdown bullet list.

    Output:
        - **Speaker Name**: What they said.
        - **Another Speaker**: Their response.
    """
    segments = _get_segments(transcript)
    lines = []

    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        text = segment.get("text", "").strip()
        if not text:
            continue

        if include_timestamps:
            timestamp = _format_timestamp(segment.get("start", 0))
            lines.append(f"- **{speaker}** [{timestamp}]: {text}")
        else:
            lines.append(f"- **{speaker}**: {text}")

    return "\n".join(lines)


def format_md_quote(transcript: dict, include_timestamps: bool = False) -> str:
    """
    Format transcript as blockquote with bold speaker names.
    This is the recommended format from the blog post for readability.

    Output:
        > **Speaker Name**: What they said.
        >
        > **Another Speaker**: Their response.
    """
    segments = _get_segments(transcript)
    lines = []

    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        text = segment.get("text", "").strip()
        if not text:
            continue

        if include_timestamps:
            timestamp = _format_timestamp(segment.get("start", 0))
            lines.append(f"> **{speaker}** [{timestamp}]: {text}")
        else:
            lines.append(f"> **{speaker}**: {text}")
        lines.append(">")  # Empty blockquote line for spacing

    # Remove trailing empty blockquote line
    if lines and lines[-1] == ">":
        lines.pop()

    return "\n".join(lines)


def _format_two_speaker_table(segments: list[dict], speakers: list[str], include_timestamps: bool) -> str:
    """Format transcript as a two-column table for exactly 2 speakers."""
    lines = [
        f"| {speakers[0]} | {speakers[1]} |",
        "| --- | --- |",
    ]

    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        text = segment.get("text", "").strip()
        if not text:
            continue

        # Escape pipe characters in text
        text = text.replace("|", "\\|")

        if include_timestamps:
            timestamp = _format_timestamp(segment.get("start", 0))
            text = f"[{timestamp}] {text}"

        col1, col2 = (text, "") if speaker == speakers[0] else ("", text)
        lines.append(f"| {col1} | {col2} |")

    return "\n".join(lines)


def _format_multi_speaker_table(segments: list[dict], include_timestamps: bool) -> str:
    """Format transcript as a multi-column table for 3+ speakers."""
    if include_timestamps:
        lines = ["| Time | Speaker | Message |", "| --- | --- | --- |"]
    else:
        lines = ["| Speaker | Message |", "| --- | --- |"]

    for segment in segments:
        speaker = segment.get("speaker", "Unknown")
        text = segment.get("text", "").strip()
        if not text:
            continue

        # Escape pipe characters in text
        text = text.replace("|", "\\|")

        if include_timestamps:
            timestamp = _format_timestamp(segment.get("start", 0))
            lines.append(f"| {timestamp} | {speaker} | {text} |")
        else:
            lines.append(f"| {speaker} | {text} |")

    return "\n".join(lines)


def format_md_table(transcript: dict, include_timestamps: bool = False) -> str:
    """
    Format transcript as a two-column markdown table.
    Best suited for conversations with exactly 2 speakers.
    Falls back to a multi-column format for more speakers.

    Output (2 speakers):
        | Speaker A | Speaker B |
        | --- | --- |
        | What A said | |
        | | What B said |

    Output (3+ speakers):
        | Time | Speaker | Message |
        | --- | --- | --- |
        | 00:00 | Speaker A | What they said |
    """
    segments = _get_segments(transcript)

    # Identify unique speakers while preserving order
    speakers = list(
        OrderedDict.fromkeys(seg.get("speaker", "Unknown") for seg in segments if seg.get("text", "").strip())
    )

    if len(speakers) == 2:
        return _format_two_speaker_table(segments, speakers, include_timestamps)
    return _format_multi_speaker_table(segments, include_timestamps)


class ListWriter:
    """Helper class to store written lines in memory."""

    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)

    def get_output(self):
        return "".join(self.lines)

    def flush(self):
        pass


def update_options(kwargs, defaults):
    """
    Helper function to update default options with values from kwargs.

    :param kwargs: Keyword arguments from the function call.
    :param defaults: Dictionary of default values.
    :return: Updated options dictionary.
    """
    options = defaults.copy()
    options.update({key: kwargs.get(key, value) for key, value in defaults.items()})
    return options


def handle_whisperx_format(transcript, writer_class, options):
    """
    Helper function to handle "srt", "vtt" and "aud" formats using whisperx writers.

    :param transcript: The transcript dictionary.
    :param writer_class: The writer class (WriteSRT, WriteVTT or WriteAudacity).
    :param options: Options for the writer.
    :return: Formatted output as a string.
    """
    writer = writer_class(output_dir=None)
    output = ListWriter()

    transcript["segments"]["language"] = transcript["language"]

    writer.write_result(transcript["segments"], output, options)

    return output.get_output()


def format_transcription(transcript, format, **kwargs) -> Response:
    """
    Format a transcript into a given format and return a FastAPI Response object.

    :param transcript: The transcript to format, a dictionary with a "segments" key that contains a list of segments with start and end times and text.
    :param format: The format to generate the transcript in. Supported formats are "json", "text", "srt", "vtt" and "aud".
    :param kwargs: Additional keyword arguments to pass to the formatter.
    :return: A FastAPI Response or JSONResponse object with the formatted transcript and appropriate media type.
    """
    # Default options, used for formats imported from whisperx.utils
    defaults = {
        "max_line_width": 1000,
        "max_line_count": None,
        "highlight_words": kwargs.get("highlight_words", False),
    }
    options = update_options(kwargs, defaults)

    if format == "json":
        response_data = {"text": transcript.get("text", "")}
        return JSONResponse(content=response_data, media_type=MediaType.APPLICATION_JSON)
    elif format == "verbose_json":
        return JSONResponse(content=transcript, media_type=MediaType.APPLICATION_JSON)
    elif format == "vtt_json":
        transcript["vtt_text"] = handle_whisperx_format(transcript, WriteVTT, options)
        return JSONResponse(content=transcript, media_type=MediaType.APPLICATION_JSON)
    elif format == "text":
        return Response(content=transcript.get("text", ""), media_type=MediaType.TEXT_PLAIN)
    elif format == "srt":
        content = handle_whisperx_format(transcript, WriteSRT, options)
        return Response(content=content, media_type=MediaType.TEXT_PLAIN)
    elif format == "vtt":
        content = handle_whisperx_format(transcript, WriteVTT, options)
        return Response(content=content, media_type=MediaType.TEXT_VTT)
    elif format == "aud":
        content = handle_whisperx_format(transcript, WriteAudacity, options)
        return Response(content=content, media_type=MediaType.TEXT_PLAIN)
    elif format == "md_basic":
        include_timestamps = kwargs.get("include_timestamps", False)
        content = format_md_basic(transcript, include_timestamps=include_timestamps)
        return Response(content=content, media_type=MediaType.TEXT_MARKDOWN)
    elif format == "md_list":
        include_timestamps = kwargs.get("include_timestamps", False)
        content = format_md_list(transcript, include_timestamps=include_timestamps)
        return Response(content=content, media_type=MediaType.TEXT_MARKDOWN)
    elif format == "md_quote":
        include_timestamps = kwargs.get("include_timestamps", False)
        content = format_md_quote(transcript, include_timestamps=include_timestamps)
        return Response(content=content, media_type=MediaType.TEXT_MARKDOWN)
    elif format == "md_table":
        include_timestamps = kwargs.get("include_timestamps", False)
        content = format_md_table(transcript, include_timestamps=include_timestamps)
        return Response(content=content, media_type=MediaType.TEXT_MARKDOWN)
    else:
        raise ValueError(f"Unsupported format: {format}")
