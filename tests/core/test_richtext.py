from django import forms
from django.template import Context, Template

from core.fields import RichTextField, TrixWidget
from core.richtext import plain_text, sanitize_html

TRIX_SAMPLE = (
    "<div><strong>Bring</strong> <em>gloves</em> and <del>no</del> water.<br>Thanks!</div>"
    "<h1>Schedule</h1><ul><li>One</li></ul><ol><li>Two</li></ol>"
    "<blockquote>Quote</blockquote><pre>code</pre>"
    '<div><a href="https://example.org/info">Info</a></div>'
)


def test_keeps_trix_formatting():
    cleaned = sanitize_html(TRIX_SAMPLE)
    for tag in (
        "<strong>",
        "<em>",
        "<del>",
        "<br>",
        "<h1>",
        "<ul>",
        "<ol>",
        "<li>",
        "<blockquote>",
        "<pre>",
    ):
        assert tag in cleaned
    assert 'href="https://example.org/info"' in cleaned
    assert 'rel="noopener noreferrer"' in cleaned


def test_sanitizing_is_idempotent():
    once = sanitize_html(TRIX_SAMPLE)
    assert sanitize_html(once) == once


def test_removes_scripts_and_event_handlers():
    cleaned = sanitize_html('<div onclick="steal()">Hi<script>alert(1)</script></div>')
    assert "script" not in cleaned
    assert "alert" not in cleaned
    assert "onclick" not in cleaned
    assert "Hi" in cleaned


def test_removes_javascript_links():
    cleaned = sanitize_html('<a href="javascript:alert(1)">click</a>')
    assert "javascript" not in cleaned
    assert "click" in cleaned


def test_removes_attachment_markup():
    attachment = (
        '<figure data-trix-attachment="{&quot;url&quot;:&quot;https://x.example/a.png&quot;}">'
        '<img src="https://x.example/a.png"><figcaption>a.png</figcaption></figure>'
    )
    cleaned = sanitize_html(attachment)
    assert "<img" not in cleaned
    assert "<figure" not in cleaned
    assert "data-trix" not in cleaned


def test_sanitize_handles_empty():
    assert sanitize_html("") == ""
    assert sanitize_html(None) == ""


def test_plain_text():
    assert plain_text(
        "<div>Hello&nbsp;<strong>there</strong></div><div>Second &amp; last</div>"
    ) == ("Hello there Second & last")
    assert plain_text("") == ""


def test_rich_text_field_sanitizes_on_save():
    field = RichTextField()
    field.set_attributes_from_name("body")

    class Row:
        body = "<div>Safe</div><script>bad()</script>"

    row = Row()
    assert field.pre_save(row, add=True) == "<div>Safe</div>"
    assert row.body == "<div>Safe</div>"


def test_rich_text_field_uses_trix_widget():
    field = RichTextField(blank=True)
    field.set_attributes_from_name("body")
    assert isinstance(field.formfield().widget, TrixWidget)


def test_trix_widget_renders_editor_bound_to_hidden_input():
    class Form(forms.Form):
        body = forms.CharField(widget=TrixWidget, required=False)

    html = str(Form(initial={"body": '<div>Hi "there"</div>'})["body"])
    assert '<input type="hidden" name="body" id="id_body"' in html
    assert '<trix-editor input="id_body"' in html
    assert "&lt;div&gt;Hi &quot;there&quot;&lt;/div&gt;" in html


def test_template_filters():
    rendered = Template(
        "{% load richtext_tags %}{{ value|rich_text }}|{{ value|excerpt:5 }}"
    ).render(Context({"value": "<div>Hello world</div><script>x()</script>"}))
    assert rendered == "<div>Hello world</div>|Hell…"
