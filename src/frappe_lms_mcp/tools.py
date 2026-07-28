"""MCP tool definitions for Frappe LMS management.

Every tool function is decorated with ``@mcp.tool()`` so they are exposed
to MCP clients.  The tools cover the full course lifecycle:

* Courses  — create, read, update, delete, list, publish
* Chapters — create, update, delete, reorder
* Lessons  — create, update content, delete, reorder
* Quizzes  — create, add questions, list, delete
* Questions — create reusable question bank entries
* Enrollments — enroll students, list, remove
* Batches — create, add courses, list
* Certificates — issue

Plus a high-level ``create_full_course`` that builds an entire course from
a single JSON definition.
"""

from __future__ import annotations

import json
from typing import Any

from .client import FrappeAPIError, FrappeClient
from .content_blocks import (
    build_content,
    code_block,
    embed_block,
    header_block,
    image_block,
    list_block,
    markdown_block,
    paragraph_block,
    quiz_block,
)

# Global singleton — created lazily by :func:`get_client`.
_client: FrappeClient | None = None


def get_client() -> FrappeClient:
    """Return the shared :class:`FrappeClient` singleton.

    Auth priority:
    1. Active connection from SQLite with API key/secret (token auth — no login needed)
    2. Active connection from SQLite with password (session auth)
    3. Environment variables (username/password or FRAPPE_API_KEY/SECRET)
    """
    global _client
    if _client is None:
        from . import db

        db.init_db()
        conn = db.get_active_connection()
        if conn:
            if conn.get("api_key") and conn.get("api_secret"):
                # Token auth — no login() call needed
                _client = FrappeClient(
                    url=conn["base_url"],
                    site=conn["site"],
                    api_key=conn["api_key"],
                    api_secret=conn["api_secret"],
                )
            elif conn.get("password"):
                # Session auth — login with stored password
                _client = FrappeClient(
                    url=conn["base_url"],
                    site=conn["site"],
                    username=conn.get("username") or "",
                    password=conn["password"],
                )
                _client.login()
            else:
                # No usable credentials in this connection — fall back to env
                _client = FrappeClient()
        else:
            # No active connection — use environment variables
            _client = FrappeClient()
    return _client


def reset_client() -> None:
    """Discard the singleton so the next :func:`get_client` re-reads config.

    Called after switching connections via the dashboard or MCP tool.
    """
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None


# ================================================================== #
#  COURSE TOOLS
# ================================================================== #


def list_courses(
    published_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    """List LMS courses.

    Args:
        published_only: If True, only return published courses.
        limit: Maximum number of courses to return (1-200).

    Returns:
        List of course dicts with name, title, short_introduction,
        published, lessons, enrollments, rating, tags, category.
    """
    client = get_client()
    limit = max(1, min(200, limit))
    filters: list = []
    if published_only:
        filters.append(["published", "=", 1])
    return client.get_list(
        "LMS Course",
        fields=[
            "name", "title", "short_introduction", "published",
            "lessons", "enrollments", "rating", "tags", "category",
            "image", "upcoming", "featured",
        ],
        filters=filters or None,
        limit_page_length=limit,
        order_by="modified desc",
    )


def get_course(course: str) -> dict:
    """Get full details of a course including its chapter/lesson outline.

    Args:
        course: The course name (slug) or title.
    """
    client = get_client()
    doc = client.get_doc("LMS Course", course)
    data = doc.get("data", doc)
    # Fetch the outline via the whitelisted utility for a richer view
    try:
        outline = client.call_method(
            "lms.lms.utils.get_course_outline", course=course
        )
        data["outline"] = outline
    except FrappeAPIError:
        pass  # outline is optional; the doc alone is still useful
    return data


def create_course(
    title: str,
    short_introduction: str,
    description: str = "",
    instructor: str = "",
    *,
    tags: str = "",
    category: str = "",
    image: str = "",
    video_link: str = "",
    published: bool = False,
    featured: bool = False,
    upcoming: bool = False,
    card_gradient: str = "",
    disable_self_learning: bool = False,
    paid_course: bool = False,
    course_price: float = 0,
    currency: str = "",
    enable_certification: bool = False,
    paid_certificate: bool = False,
) -> dict:
    """Create a new LMS Course.

    Args:
        title: Course title (required).  A URL slug is auto-generated from this.
        short_introduction: One-line summary shown on course cards (required).
        description: Full HTML description of the course.
        instructor: Email/User ID of the instructor.  Defaults to the logged-in user.
        tags: Comma-separated tags, e.g. "Python, Web, Beginner".
        category: Category name (must exist in LMS Category doctype).
        image: Path to preview image, e.g. "/assets/lms/images/foo.jpeg".
        video_link: YouTube video ID or embed URL for the promo video.
        published: Whether the course is immediately published.
        featured: Mark as a featured course.
        upcoming: Mark as an upcoming course.
        card_gradient: Card colour: Red/Blue/Green/Amber/Cyan/Orange/Pink/Purple/Teal/Violet/Yellow/Gray.
        disable_self_learning: If True, students can only learn via batches.
        paid_course: Whether this is a paid course.
        course_price: Price amount (required if paid_course).
        currency: Currency code (required if paid_course), e.g. "USD" or "IDR".
        enable_certification: Enable completion certificate.
        paid_certificate: Certificate requires payment.

    Returns:
        The created course document.
    """
    client = get_client()
    data: dict[str, Any] = {
        "title": title,
        "short_introduction": short_introduction,
        "description": description,
    }
    # Frappe LMS requires at least one instructor. If none is given,
    # default to the currently logged-in user.
    instructor_email = instructor or client.get_current_user()
    if instructor_email:
        data["instructors"] = [{"instructor": instructor_email}]
    if tags:
        data["tags"] = tags
    if category:
        data["category"] = category
    if image:
        data["image"] = image
    if video_link:
        data["video_link"] = video_link
    if published:
        data["published"] = 1
    if featured:
        data["featured"] = 1
    if upcoming:
        data["upcoming"] = 1
    if card_gradient:
        data["card_gradient"] = card_gradient
    if disable_self_learning:
        data["disable_self_learning"] = 1
    if paid_course:
        data["paid_course"] = 1
        data["course_price"] = course_price
        if currency:
            data["currency"] = currency
    if enable_certification:
        data["enable_certification"] = 1
    if paid_certificate:
        data["paid_certificate"] = 1

    return client.insert("LMS Course", data)


def update_course(course: str, **fields: Any) -> dict:
    """Update fields on an existing course.

    Args:
        course: The course name (slug).
        **fields: Any writable field on LMS Course (e.g. title="New Title",
                  published=True, short_introduction="...", tags="a,b").

    Returns:
        The updated course document.
    """
    client = get_client()
    # Convert bools to ints for Frappe Check fields
    normalised: dict[str, Any] = {}
    for k, v in fields.items():
        if isinstance(v, bool):
            normalised[k] = 1 if v else 0
        else:
            normalised[k] = v
    return client.update("LMS Course", course, normalised)


def delete_course(course: str) -> str:
    """Delete a course and all its chapters, lessons, and enrollments.

    Args:
        course: The course name (slug).

    Returns:
        Confirmation message.
    """
    client = get_client()
    try:
        client.call_method("lms.lms.api.delete_course", course=course)
        return f"Course '{course}' deleted successfully."
    except FrappeAPIError:
        # Fallback to direct resource deletion
        client.delete("LMS Course", course)
        return f"Course '{course}' deleted."


def publish_course(course: str, published: bool = True) -> dict:
    """Toggle the published status of a course.

    Args:
        course: The course name (slug).
        published: True to publish, False to unpublish.
    """
    client = get_client()
    fields: dict[str, Any] = {"published": 1 if published else 0}
    if published:
        from datetime import date

        fields["published_on"] = date.today().isoformat()
    return client.update("LMS Course", course, fields)


# ================================================================== #
#  CHAPTER TOOLS
# ================================================================== #


def create_chapter(course: str, title: str, idx: int | None = None) -> dict:
    """Create a chapter in a course and link it to the course outline.

    Args:
        course: The course name (slug).
        title: Chapter title.
        idx: Position in the course outline (0-based).  If None, appends to end.

    Returns:
        The created chapter document.
    """
    client = get_client()
    # Use the whitelisted upsert_chapter API for atomic creation + linking
    result = client.call_method(
        "lms.lms.api.upsert_chapter",
        title=title,
        course=course,
        is_scorm_package=False,
    )
    if isinstance(result, str):
        return {"name": result, "title": title, "course": course}
    return result if isinstance(result, dict) else {"name": str(result), "title": title, "course": course}


def get_chapter(chapter: str) -> dict:
    """Get a chapter with its lessons.

    Args:
        chapter: The chapter name.
    """
    client = get_client()
    doc = client.get_doc("Course Chapter", chapter)
    return doc.get("data", doc)


def update_chapter(chapter: str, title: str | None = None) -> dict:
    """Update a chapter (currently only the title can be changed).

    Args:
        chapter: The chapter name.
        title: New chapter title.
    """
    client = get_client()
    # upsert_chapter handles updates when name is provided
    course = client.get_value("Course Chapter", chapter, ["course"]).get("course")
    return client.call_method(
        "lms.lms.api.upsert_chapter",
        title=title or "",
        course=course,
        is_scorm_package=False,
        name=chapter,
    )


def delete_chapter(chapter: str) -> str:
    """Delete a chapter and all its lessons.

    Args:
        chapter: The chapter name.

    Returns:
        Confirmation message.
    """
    client = get_client()
    client.call_method("lms.lms.api.delete_chapter", chapter=chapter)
    return f"Chapter '{chapter}' and its lessons deleted."


def reorder_chapter(course: str, chapter: str, idx: int) -> str:
    """Move a chapter to a new position in the course outline.

    Args:
        course: The course name (slug).
        chapter: The chapter name.
        idx: New 0-based position.
    """
    client = get_client()
    client.call_method(
        "lms.lms.api.update_chapter_index",
        chapter=chapter,
        course=course,
        idx=idx,
    )
    return f"Chapter '{chapter}' moved to position {idx}."


# ================================================================== #
#  LESSON TOOLS
# ================================================================== #


def create_lesson(chapter: str, title: str, content: str = "") -> dict:
    """Create a lesson in a chapter.

    Inserts the ``Course Lesson`` document directly (with the correct title so
    the auto-generated name includes it), then appends a ``Lesson Reference``
    child row to the chapter's lessons table.

    Args:
        chapter: The chapter name.
        title: Lesson title.
        content: EditorJS JSON string for the lesson body.  Use
                 ``build_lesson_content`` to construct this.

    Returns:
        The created lesson document.
    """
    client = get_client()
    # Look up the course from the chapter
    chapter_doc = client.get_value("Course Chapter", chapter, ["course"])
    course = chapter_doc.get("course")
    if not course:
        raise ValueError(f"Chapter '{chapter}' has no linked course.")

    # Insert the lesson directly with the correct title (so the autoname
    # format "{####} {title}" produces a meaningful document name).
    lesson_data: dict[str, Any] = {
        "title": title,
        "chapter": chapter,
        "course": course,
    }
    if content:
        lesson_data["content"] = content
    lesson = client.insert("Course Lesson", lesson_data)
    lesson_name = lesson.get("name", lesson.get("data", {}).get("name"))

    # Append a Lesson Reference to the chapter's lessons child table.
    chapter_full = client.get_doc("Course Chapter", chapter)
    ch_data = chapter_full.get("data", chapter_full)
    lessons_list = ch_data.get("lessons", [])
    lessons_list.append({"lesson": lesson_name})
    client.update("Course Chapter", chapter, {"lessons": lessons_list})

    return lesson


def get_lesson(lesson: str) -> dict:
    """Get a lesson with its content and metadata.

    Args:
        lesson: The lesson name.
    """
    client = get_client()
    doc = client.get_doc("Course Lesson", lesson)
    return doc.get("data", doc)


def update_lesson(
    lesson: str,
    title: str | None = None,
    content: str | None = None,
    youtube: str | None = None,
    include_in_preview: bool | None = None,
    instructor_notes: str | None = None,
) -> dict:
    """Update a lesson's fields.

    Args:
        lesson: The lesson name.
        title: New lesson title.
        content: EditorJS JSON string (use ``build_lesson_content`` to build).
        youtube: YouTube video URL (legacy field, renders at top of lesson).
        include_in_preview: Whether this lesson is visible in the course preview.
        instructor_notes: Markdown instructor notes.

    Returns:
        The updated lesson document.
    """
    client = get_client()
    data: dict[str, Any] = {}
    if title is not None:
        data["title"] = title
    if content is not None:
        data["content"] = content
    if youtube is not None:
        data["youtube"] = youtube
    if include_in_preview is not None:
        data["include_in_preview"] = 1 if include_in_preview else 0
    if instructor_notes is not None:
        data["instructor_notes"] = instructor_notes
    if not data:
        raise ValueError("At least one field must be provided to update.")
    return client.update("Course Lesson", lesson, data)


def delete_lesson(lesson: str, chapter: str) -> str:
    """Delete a lesson and remove it from the chapter.

    Args:
        lesson: The lesson name.
        chapter: The chapter name (needed to clean up the Lesson Reference).

    Returns:
        Confirmation message.
    """
    client = get_client()
    client.call_method("lms.lms.api.delete_lesson", lesson=lesson, chapter=chapter)
    return f"Lesson '{lesson}' deleted."


def move_lesson(
    lesson: str,
    source_chapter: str,
    target_chapter: str,
    idx: int,
) -> str:
    """Move a lesson to a different chapter or reorder within the same chapter.

    Args:
        lesson: The lesson name.
        source_chapter: The chapter the lesson currently belongs to.
        target_chapter: The destination chapter (same as source to reorder).
        idx: New 0-based position within the target chapter.
    """
    client = get_client()
    client.call_method(
        "lms.lms.api.update_lesson_index",
        lesson=lesson,
        sourceChapter=source_chapter,
        targetChapter=target_chapter,
        idx=idx,
    )
    return f"Lesson '{lesson}' moved to position {idx} in '{target_chapter}'."


# ================================================================== #
#  LESSON CONTENT BUILDERS
# ================================================================== #


def build_lesson_content(
    paragraphs: list[str] | None = None,
    *,
    headers: list[dict] | None = None,
    lists: list[dict] | None = None,
    images: list[dict] | None = None,
    code: list[dict] | None = None,
    embeds: list[dict] | None = None,
    quiz_refs: list[str] | None = None,
    markdown: list[str] | None = None,
) -> str:
    """Build an EditorJS JSON content string for a lesson.

    This is a convenience wrapper around the content_blocks module.
    Each parameter is an optional list; blocks are assembled in the order:
    headers, paragraphs, lists, images, code, embeds, quiz_refs, markdown.

    Args:
        paragraphs: List of paragraph text strings.
        headers: List of ``{"text": "...", "level": 2}`` dicts.
        lists: List of ``{"items": [...], "ordered": False}`` dicts.
        images: List of ``{"url": "...", "caption": "..."}`` dicts.
        code: List of ``{"code": "...", "language": "python"}`` dicts.
        embeds: List of ``{"service": "youtube", "source": "url", "embed": "id"}`` dicts.
        quiz_refs: List of LMS Quiz names to embed.
        markdown: List of raw markdown strings.

    Returns:
        JSON string ready for the ``content`` field of a Course Lesson.
    """
    blocks: list[dict] = []
    for h in headers or []:
        blocks.append(header_block(h["text"], h.get("level", 2)))
    for p in paragraphs or []:
        blocks.append(paragraph_block(p))
    for lst in lists or []:
        blocks.append(list_block(lst["items"], ordered=lst.get("ordered", False)))
    for img in images or []:
        blocks.append(image_block(img["url"], img.get("caption", "")))
    for c in code or []:
        blocks.append(code_block(c["code"], c.get("language", "plaintext")))
    for emb in embeds or []:
        blocks.append(embed_block(
            emb["service"],
            emb["source"],
            emb.get("embed"),
            emb.get("caption", ""),
        ))
    for q in quiz_refs or []:
        blocks.append(quiz_block(q))
    for md in markdown or []:
        blocks.append(markdown_block(md))
    return build_content(blocks)


def add_paragraph_to_content(existing_content: str, text: str) -> str:
    """Append a paragraph to an existing EditorJS content string.

    Args:
        existing_content: Current EditorJS JSON string.
        text: Paragraph text to append.

    Returns:
        Updated EditorJS JSON string.
    """
    doc = json.loads(existing_content) if existing_content else {"blocks": []}
    doc.setdefault("blocks", []).append(paragraph_block(text))
    return build_content(doc["blocks"])


# ================================================================== #
#  QUIZ & QUESTION TOOLS
# ================================================================== #


def create_question(
    question: str,
    question_type: str = "Choices",
    *,
    options: list[dict] | None = None,
    possibilities: list[str] | None = None,
) -> dict:
    """Create a reusable LMS Question.

    Args:
        question: The question text (HTML allowed).
        question_type: "Choices", "User Input", or "Open Ended".
        options: For "Choices" type: list of ``{"text": "...", "correct": bool, "explanation": "..."}``.
                 Up to 10 options.  At least one must be correct.
        possibilities: For "User Input" type: list of acceptable answer strings.

    Returns:
        The created question document.
    """
    client = get_client()
    data: dict[str, Any] = {
        "question": question,
        "type": question_type,
    }
    if question_type == "Choices":
        if not options:
            raise ValueError("'options' is required for Choices type.")
        for i, opt in enumerate(options[:10], start=1):
            data[f"option_{i}"] = opt["text"]
            data[f"is_correct_{i}"] = 1 if opt.get("correct") else 0
            if opt.get("explanation"):
                data[f"explanation_{i}"] = opt["explanation"]
    elif question_type == "User Input":
        if not possibilities:
            raise ValueError("'possibilities' is required for User Input type.")
        for i, p in enumerate(possibilities[:10], start=1):
            data[f"possibility_{i}"] = p
    return client.insert("LMS Question", data)


def create_quiz(
    title: str,
    passing_percentage: int = 70,
    *,
    questions: list[dict] | None = None,
    max_attempts: int = 0,
    show_answers: bool = True,
    duration: str = "",
    shuffle_questions: bool = False,
    enable_negative_marking: bool = False,
    marks_to_cut: int = 1,
) -> dict:
    """Create an LMS Quiz with optional questions.

    Args:
        title: Quiz title (slug auto-generated).
        passing_percentage: Minimum percentage to pass (0-100).
        questions: List of ``{"question": "<LMS Question name>", "marks": 5}``.
                   If the question doesn't exist yet, create it first with
                   ``create_question``.
        max_attempts: Max attempts (0 = unlimited).
        show_answers: Show correct answers after submission.
        duration: Time limit in minutes (as string), e.g. "30".
        shuffle_questions: Randomise question order.
        enable_negative_marking: Deduct marks for wrong answers.
        marks_to_cut: Marks to deduct per wrong answer (if negative marking enabled).

    Returns:
        The created quiz document.
    """
    client = get_client()
    data: dict[str, Any] = {
        "title": title,
        "passing_percentage": passing_percentage,
        "max_attempts": max_attempts,
        "show_answers": 1 if show_answers else 0,
    }
    if duration:
        data["duration"] = duration
    if shuffle_questions:
        data["shuffle_questions"] = 1
    if enable_negative_marking:
        data["enable_negative_marking"] = 1
        data["marks_to_cut"] = marks_to_cut
    if questions:
        data["questions"] = [
            {"question": q["question"], "marks": q.get("marks", 1)}
            for q in questions
        ]
    return client.insert("LMS Quiz", data)


def add_question_to_quiz(quiz: str, question: str, marks: int = 1) -> dict:
    """Add an existing question to a quiz.

    Args:
        quiz: The quiz name (slug).
        question: The LMS Question name.
        marks: Marks for this question in the quiz.

    Returns:
        The updated quiz document.
    """
    client = get_client()
    quiz_doc = client.get_doc("LMS Quiz", quiz)
    data = quiz_doc.get("data", quiz_doc)
    existing_questions = data.get("questions", [])
    existing_questions.append({"question": question, "marks": marks})
    return client.update("LMS Quiz", quiz, {"questions": existing_questions})


def get_quiz(quiz: str, *, with_questions: bool = True) -> dict:
    """Get a quiz, optionally with full question details.

    Args:
        quiz: The quiz name (slug).
        with_questions: If True, fetch full question text and options for
                         each linked question (requires quiz access).
    """
    client = get_client()
    # Always fetch the quiz doc (includes the questions child table with
    # question references and marks).
    doc = client.get_doc("LMS Quiz", quiz)
    data = doc.get("data", doc)
    if not with_questions:
        return data
    # Enrich with full question details via the whitelisted utility.
    try:
        enriched = client.call_method(
            "lms.lms.utils.get_quiz_with_questions", quiz=quiz
        )
        if isinstance(enriched, dict) and enriched.get("questions_by_name"):
            # Merge question details into the child table rows
            qbn = enriched["questions_by_name"]
            for row in data.get("questions", []):
                qname = row.get("question")
                if qname and qname in qbn:
                    row["question_detail"] = qbn[qname].get("question")
                    row["question_type"] = qbn[qname].get("type")
                    row["options"] = {
                        k: v for k, v in qbn[qname].items()
                        if k.startswith("option_") and v
                    }
                    row["correct"] = {
                        k: v for k, v in qbn[qname].items()
                        if k.startswith("is_correct_") and v
                    }
    except FrappeAPIError:
        pass  # enrichment is optional; return the doc as-is
    return data


def list_quizzes(limit: int = 50) -> list[dict]:
    """List all quizzes.

    Args:
        limit: Maximum number of quizzes to return.
    """
    client = get_client()
    return client.get_list(
        "LMS Quiz",
        fields=["name", "title", "passing_percentage", "total_marks",
                "max_attempts", "lesson", "course"],
        limit_page_length=limit,
        order_by="modified desc",
    )


def delete_quiz(quiz: str) -> str:
    """Delete a quiz.

    Args:
        quiz: The quiz name (slug).
    """
    client = get_client()
    client.delete("LMS Quiz", quiz)
    return f"Quiz '{quiz}' deleted."


def embed_quiz_in_lesson(lesson: str, quiz: str) -> dict:
    """Embed a quiz into a lesson's content as an EditorJS quiz block.

    This appends a quiz block to the lesson's existing content.

    Args:
        lesson: The lesson name.
        quiz: The quiz name (slug).

    Returns:
        The updated lesson document.
    """
    client = get_client()
    lesson_doc = client.get_doc("Course Lesson", lesson)
    data = lesson_doc.get("data", lesson_doc)
    existing_content = data.get("content", "")
    doc = json.loads(existing_content) if existing_content else {"blocks": []}
    doc.setdefault("blocks", []).append(quiz_block(quiz))
    new_content = build_content(doc["blocks"])
    return client.update("Course Lesson", lesson, {"content": new_content})


# ================================================================== #
#  ENROLLMENT TOOLS
# ================================================================== #


def enroll_student(course: str, student: str, member_type: str = "Student") -> dict:
    """Enroll a student in a course.

    Args:
        course: The course name (slug).
        student: The User email/ID of the student.
        member_type: "Student", "Mentor", or "Staff".

    Returns:
        The created enrollment document.
    """
    client = get_client()
    return client.insert("LMS Enrollment", {
        "member": student,
        "course": course,
        "member_type": member_type,
    })


def list_enrollments(course: str | None = None, student: str | None = None,
                     limit: int = 100) -> list[dict]:
    """List enrollments, optionally filtered by course or student.

    Args:
        course: Filter by course name.
        student: Filter by student (User email/ID).
        limit: Maximum results.
    """
    client = get_client()
    filters: list = []
    if course:
        filters.append(["course", "=", course])
    if student:
        filters.append(["member", "=", student])
    return client.get_list(
        "LMS Enrollment",
        fields=["name", "member", "member_name", "course", "progress",
                "member_type", "role", "creation"],
        filters=filters or None,
        limit_page_length=limit,
        order_by="creation desc",
    )


def unenroll_student(enrollment: str) -> str:
    """Remove a student's enrollment.

    Args:
        enrollment: The enrollment name.
    """
    client = get_client()
    client.delete("LMS Enrollment", enrollment)
    return f"Enrollment '{enrollment}' removed."


# ================================================================== #
#  BATCH TOOLS
# ================================================================== #


def create_batch(
    title: str,
    start_date: str,
    end_date: str,
    start_time: str,
    end_time: str,
    timezone: str,
    description: str,
    batch_details: str,
    instructor: str,
    *,
    courses: list[str] | None = None,
    published: bool = False,
    allow_self_enrollment: bool = False,
    seat_count: int = 0,
    medium: str = "Online",
    paid_batch: bool = False,
    amount: float = 0,
    currency: str = "",
    category: str = "",
) -> dict:
    """Create an LMS Batch (cohort).

    Args:
        title: Batch title (slug auto-generated).
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        start_time: Start time (HH:MM:SS).
        end_time: End time (HH:MM:SS).
        timezone: Timezone, e.g. "Asia/Jakarta".
        description: Short description.
        batch_details: Full HTML details.
        instructor: Instructor User email/ID.
        courses: List of course names to include in the batch.
        published: Whether the batch is published.
        allow_self_enrollment: Allow students to self-enroll.
        seat_count: Number of seats (0 = unlimited).
        medium: "Online" or "Offline".
        paid_batch: Whether this is a paid batch.
        amount: Price amount (required if paid_batch).
        currency: Currency code (required if paid_batch).
        category: Category name.

    Returns:
        The created batch document.
    """
    client = get_client()
    data: dict[str, Any] = {
        "title": title,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "timezone": timezone,
        "description": description,
        "batch_details": batch_details,
        "instructors": [{"instructor": instructor}],
        "medium": medium,
    }
    if courses:
        data["courses"] = [{"course": c} for c in courses]
    if published:
        data["published"] = 1
    if allow_self_enrollment:
        data["allow_self_enrollment"] = 1
    if seat_count:
        data["seat_count"] = seat_count
    if category:
        data["category"] = category
    if paid_batch:
        data["paid_batch"] = 1
        data["amount"] = amount
        if currency:
            data["currency"] = currency
    return client.insert("LMS Batch", data)


def list_batches(limit: int = 50) -> list[dict]:
    """List LMS batches.

    Args:
        limit: Maximum results.
    """
    client = get_client()
    return client.get_list(
        "LMS Batch",
        fields=["name", "title", "start_date", "end_date", "published",
                "seat_count", "medium", "category"],
        limit_page_length=limit,
        order_by="start_date desc",
    )


# ================================================================== #
#  CERTIFICATE TOOLS
# ================================================================== #


def issue_certificate(course: str, member: str, template: str,
                      issue_date: str | None = None,
                      expiry_date: str | None = None) -> dict:
    """Manually issue a certificate to a member for a course.

    Args:
        course: The course name (slug).
        member: The User email/ID.
        template: The Print Format name to use as the certificate template.
        issue_date: Issue date (YYYY-MM-DD).  Defaults to today.
        expiry_date: Expiry date (YYYY-MM-DD), optional.

    Returns:
        The created certificate document.
    """
    client = get_client()
    data: dict[str, Any] = {
        "member": member,
        "course": course,
        "template": template,
    }
    if issue_date:
        data["issue_date"] = issue_date
    if expiry_date:
        data["expiry_date"] = expiry_date
    return client.insert("LMS Certificate", data)


# ================================================================== #
#  HIGH-LEVEL: CREATE FULL COURSE FROM A SPEC
# ================================================================== #


def create_full_course(spec: dict) -> dict:
    """Create a complete course with chapters, lessons, and quizzes from a
    single JSON specification.

    This is the main tool for AI agents to build comprehensive courses in
    one call.  The spec format:

    .. code-block:: json

        {
          "title": "Introduction to Python",
          "short_introduction": "Learn Python from scratch",
          "description": "<p>A comprehensive Python course</p>",
          "instructor": "admin@example.com",
          "tags": "Python, Programming, Beginner",
          "category": "Programming",
          "published": false,
          "chapters": [
            {
              "title": "Getting Started",
              "lessons": [
                {
                  "title": "Why Python?",
                  "content": {
                    "paragraphs": ["Python is..."],
                    "headers": [{"text": "Overview", "level": 2}]
                  }
                },
                {
                  "title": "Quiz: Python Basics",
                  "content": {"paragraphs": ["Test your knowledge"]},
                  "quiz": {
                    "title": "Python Basics Quiz",
                    "passing_percentage": 70,
                    "questions": [
                      {
                        "question": "Is Python compiled?",
                        "type": "Choices",
                        "options": [
                          {"text": "Yes", "correct": false},
                          {"text": "No, interpreted", "correct": true}
                        ]
                      }
                    ]
                  }
                }
              ]
            }
          ]
        }

    The ``content`` for each lesson can contain: ``paragraphs``, ``headers``,
    ``lists``, ``images``, ``code``, ``embeds``, ``markdown``, and
    ``quiz_refs``.  If a lesson has a ``quiz`` key, the quiz is created
    and embedded as a block in that lesson.

    Args:
        spec: The full course specification dict.

    Returns:
        Dict with ``course`` (name), ``chapters`` (list of names),
        ``lessons`` (list of names), ``quizzes`` (list of names).
    """
    client = get_client()
    results: dict[str, Any] = {
        "course": None,
        "chapters": [],
        "lessons": [],
        "quizzes": [],
    }

    # 1. Create the course
    course_kwargs: dict[str, Any] = {
        "title": spec["title"],
        "short_introduction": spec["short_introduction"],
        "description": spec.get("description", ""),
        "instructor": spec.get("instructor", ""),
    }
    for opt_field in [
        "tags", "category", "image", "video_link", "card_gradient",
    ]:
        if opt_field in spec:
            course_kwargs[opt_field] = spec[opt_field]
    if spec.get("published"):
        course_kwargs["published"] = True
    if spec.get("featured"):
        course_kwargs["featured"] = True
    if spec.get("upcoming"):
        course_kwargs["upcoming"] = True
    if spec.get("enable_certification"):
        course_kwargs["enable_certification"] = True

    course_doc = create_course(**course_kwargs)
    course_name = course_doc.get("name", course_doc.get("data", {}).get("name"))
    results["course"] = course_name

    # 2. Create chapters and lessons
    for ch_idx, chapter_spec in enumerate(spec.get("chapters", [])):
        chapter_doc = create_chapter(
            course=course_name,
            title=chapter_spec["title"],
        )
        chapter_name = chapter_doc.get("name") if isinstance(chapter_doc, dict) else str(chapter_doc)
        results["chapters"].append(chapter_name)

        for lesson_spec in chapter_spec.get("lessons", []):
            # Build content if provided
            content = ""
            content_spec = lesson_spec.get("content")
            if content_spec and isinstance(content_spec, dict):
                content = build_lesson_content(**content_spec)

            lesson_doc = create_lesson(
                chapter=chapter_name,
                title=lesson_spec["title"],
                content=content,
            )
            lesson_name = (
                lesson_doc.get("name", lesson_doc.get("data", {}).get("name"))
                if isinstance(lesson_doc, dict)
                else str(lesson_doc)
            )
            results["lessons"].append(lesson_name)

            # Create and embed quiz if specified
            quiz_spec = lesson_spec.get("quiz")
            if quiz_spec:
                questions = []
                for q_spec in quiz_spec.get("questions", []):
                    q_doc = create_question(
                        question=q_spec["question"],
                        question_type=q_spec.get("type", "Choices"),
                        options=q_spec.get("options"),
                        possibilities=q_spec.get("possibilities"),
                    )
                    q_name = q_doc.get("name", q_doc.get("data", {}).get("name"))
                    questions.append({
                        "question": q_name,
                        "marks": q_spec.get("marks", 1),
                    })

                quiz_doc = create_quiz(
                    title=quiz_spec["title"],
                    passing_percentage=quiz_spec.get("passing_percentage", 70),
                    questions=questions,
                    max_attempts=quiz_spec.get("max_attempts", 0),
                    show_answers=quiz_spec.get("show_answers", True),
                    duration=quiz_spec.get("duration", ""),
                    shuffle_questions=quiz_spec.get("shuffle_questions", False),
                )
                quiz_name = quiz_doc.get("name", quiz_doc.get("data", {}).get("name"))
                results["quizzes"].append(quiz_name)

                # Embed the quiz in the lesson
                embed_quiz_in_lesson(lesson_name, quiz_name)

            # Set preview flag if specified
            if lesson_spec.get("include_in_preview"):
                update_lesson(lesson_name, include_in_preview=True)

    # 3. Auto-cache the course spec to SQLite for future re-upload
    try:
        from . import db

        db.init_db()
        active = db.get_active_connection()
        if active:
            db.cache_course(
                connection_id=active["id"],
                frappe_course_id=course_name or "",
                title=spec["title"],
                slug=course_name or "",
                chapter_count=len(results["chapters"]),
                lesson_count=len(results["lessons"]),
                quiz_count=len(results["quizzes"]),
                spec_json=json.dumps(spec, ensure_ascii=False),
            )
            db.log_operation(
                connection_id=active["id"],
                operation="create",
                entity_type="course",
                entity_name=course_name or "",
                details={
                    "title": spec["title"],
                    "chapters": len(results["chapters"]),
                    "lessons": len(results["lessons"]),
                    "quizzes": len(results["quizzes"]),
                },
            )
    except Exception:
        # Caching is best-effort — don't fail the course creation
        pass

    return results


# ================================================================== #
#  CONNECTION & CACHE TOOLS (SQLite-backed)
# ================================================================== #


def list_connections() -> list[dict]:
    """List all saved Frappe LMS connections from the local database.

    Returns connections with the active one first.  API secrets are masked.
    """
    from . import db

    db.init_db()
    return db.list_connections()


def switch_connection(name: str) -> dict:
    """Switch the active Frappe LMS connection by name.

    Args:
        name: The connection name (label) to activate.

    Returns:
        Dict with the activated connection details and ``ok`` status.
    """
    from . import db

    db.init_db()
    conn = db.get_connection_by_name(name)
    if not conn:
        return {"ok": False, "error": f"Connection '{name}' not found"}
    db.set_active_connection(conn["id"])
    # Discard the old singleton so the next call re-creates with new creds
    reset_client()
    return {"ok": True, "active_connection": name, "base_url": conn["base_url"]}


def list_cached_courses(connection_name: str = "") -> list[dict]:
    """List courses cached in the local SQLite database.

    These are courses previously created or imported.  Use this to find a
    course by ID for re-upload without querying Frappe.

    Args:
        connection_name: Filter by connection name.  Empty = all connections.

    Returns:
        List of cached course dicts with ``id``, ``title``, ``frappe_course_id``,
        ``chapter_count``, ``lesson_count``, ``quiz_count``, ``connection_name``.
    """
    from . import db

    db.init_db()
    if connection_name:
        conn = db.get_connection_by_name(connection_name)
        if not conn:
            return []
        return db.list_cached_courses(conn["id"])
    return db.list_cached_courses()


def get_cached_course(course_id: int) -> dict | None:
    """Get full details of a cached course, including its JSON spec.

    Args:
        course_id: The cache ID (from :func:`list_cached_courses`).

    Returns:
        Dict with all cached fields including ``spec_json`` (the full
        ``create_full_course`` spec that can be re-uploaded).
    """
    from . import db

    db.init_db()
    return db.get_cached_course(course_id)


def reupload_course(course_id: int, connection_name: str = "") -> dict:
    """Re-upload a cached course to a Frappe LMS instance.

    Uses the stored JSON spec from the cache to recreate the course on the
    specified (or active) connection.  Useful for migrating courses between
    Frappe instances.

    Args:
        course_id: The cache ID of the course to re-upload.
        connection_name: Target connection name.  Empty = active connection.

    Returns:
        The ``create_full_course`` result dict with the new course name.
    """
    from . import db

    db.init_db()
    cached = db.get_cached_course(course_id)
    if not cached:
        return {"ok": False, "error": f"Cached course {course_id} not found"}

    spec = json.loads(cached.get("spec_json", "{}"))
    if not spec:
        return {"ok": False, "error": "Cached course has no spec_json"}

    # Optionally switch to a different connection for the upload
    switched = False
    if connection_name:
        target = db.get_connection_by_name(connection_name)
        if not target:
            return {"ok": False, "error": f"Connection '{connection_name}' not found"}
        db.set_active_connection(target["id"])
        reset_client()
        switched = True

    try:
        result = create_full_course(spec)

        # Cache on the target connection too
        active = db.get_active_connection()
        if active:
            new_name = result.get("course", "")
            db.cache_course(
                connection_id=active["id"],
                frappe_course_id=new_name,
                title=spec["title"],
                slug=new_name,
                chapter_count=len(result.get("chapters", [])),
                lesson_count=len(result.get("lessons", [])),
                quiz_count=len(result.get("quizzes", [])),
                spec_json=json.dumps(spec, ensure_ascii=False),
            )
            db.log_operation(
                connection_id=active["id"],
                operation="reupload",
                entity_type="course",
                entity_name=new_name,
                details={"source_cache_id": course_id, "source_title": cached["title"]},
            )
        return {"ok": True, **result}
    finally:
        # If we switched, switch back to the original connection
        if switched:
            # The original active connection is whatever was active before;
            # we can't easily track it, so we just leave the new one active.
            pass


def import_course_from_frappe(course_slug: str) -> dict:
    """Import a course from Frappe into the local cache.

    Fetches the course outline from the active Frappe connection and stores
    its metadata in SQLite.  Note: this caches metadata only (not full lesson
    content); use :func:`reupload_course` for full spec re-upload.

    Args:
        course_slug: The Frappe course name (slug).

    Returns:
        Dict with the cached course info.
    """
    from . import db

    db.init_db()
    # Fetch course details from Frappe
    details = get_course(course_slug)
    active = db.get_active_connection()
    if not active:
        return {"ok": False, "error": "No active connection in database"}

    title = details.get("title", course_slug)
    outline = details.get("outline", [])
    chapter_count = len(outline)
    lesson_count = sum(len(ch.get("lessons", [])) for ch in outline)
    quiz_count = 0  # Would need to inspect lessons for quizzes

    cached = db.cache_course(
        connection_id=active["id"],
        frappe_course_id=course_slug,
        title=title,
        slug=course_slug,
        chapter_count=chapter_count,
        lesson_count=lesson_count,
        quiz_count=quiz_count,
        spec_json="",  # Import doesn't reconstruct the full spec
    )
    db.log_operation(
        connection_id=active["id"],
        operation="import",
        entity_type="course",
        entity_name=course_slug,
        details={"title": title},
    )
    return {"ok": True, "cached": cached}


def list_operation_logs(limit: int = 50) -> list[dict]:
    """List recent operations from the audit log.

    Args:
        limit: Maximum number of entries to return (most recent first).

    Returns:
        List of operation log dicts.
    """
    from . import db

    db.init_db()
    return db.list_operations(limit)
