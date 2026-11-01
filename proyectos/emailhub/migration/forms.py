from django import forms


class AccountForm(forms.Form):
    """IMAP connection details for one mailbox (used with prefixes src/ dst)."""

    label = forms.CharField(max_length=200, required=False)
    host = forms.CharField(max_length=255)
    port = forms.IntegerField(initial=993, min_value=1, max_value=65535)
    use_ssl = forms.BooleanField(initial=True, required=False)
    username = forms.CharField(max_length=255, label="Email / username")
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True),
        help_text="Use an app password, not your normal login password.",
    )


PROVIDER_PRESETS = {
    "gmail.com": ("imap.gmail.com", 993),
    "googlemail.com": ("imap.gmail.com", 993),
    "outlook.com": ("outlook.office365.com", 993),
    "hotmail.com": ("outlook.office365.com", 993),
    "office365.com": ("outlook.office365.com", 993),
    "yahoo.com": ("imap.mail.yahoo.com", 993),
    "icloud.com": ("imap.mail.me.com", 993),
    "fastmail.com": ("imap.fastmail.com", 993),
}
