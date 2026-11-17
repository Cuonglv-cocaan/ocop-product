"""Chat presentation and shared interaction states."""

COLOR_TOKENS = """:root {
    --ocop-text-primary:#183d2b;
    --ocop-text-product:#183d2b;
    --ocop-text-muted:#53675b;
    --ocop-text-accent:#276e48;
    --ocop-text-on-accent:#ffffff;
    --ocop-surface-product:#ffffff;
}"""

CHAT_STYLES = '<style>' + COLOR_TOKENS + """
[data-testid="stChatMessage"] {border-radius:16px;padding:18px;gap:12px;min-width:0;}
[data-testid="stChatMessage"]:has(.ocop-assistant-label) {
    background:#f0f8f2;border:1px solid #cce3d2;border-left:4px solid #287a4d;
    box-shadow:0 3px 12px rgba(18,62,43,.06);
}
[data-testid="stChatMessage"]:has(.ocop-user-label) {background:#f5f6f8;border:1px solid #e7e9ed;}
[data-testid="stChatMessageContent"] {min-width:0;width:100%;}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {line-height:1.8;color:#163d2b;}
.ocop-assistant-label,.ocop-user-label {font-size:12px;font-weight:800;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;}
.ocop-assistant-label {color:#216b43;}
.ocop-user-label {color:#637185;}
.chat-products-heading {font-size:13px;font-weight:750;color:#234d36;margin:18px 0 10px;}
[class*="st-key-"][class*="_suggestions"] {container-type:inline-size;margin:4px 0 8px;}
[class*="st-key-"][class*="_suggestions"] [data-testid="stHorizontalBlock"] {
    display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;align-items:stretch;
}
[class*="st-key-"][class*="_suggestions"] [data-testid="stColumn"] {
    width:100%!important;min-width:0!important;
}
[class*="st-key-"][class*="_suggestions"] [data-testid="stButton"] button {
    width:100%;height:104px;background:#fff;border:1px solid #dce8df;border-radius:14px;
    color:#195b3e;text-align:left;justify-content:flex-start;align-items:flex-start;
    gap:12px;padding:18px;box-shadow:0 2px 5px rgba(18,62,43,.035);
}
[class*="st-key-"][class*="_suggestions"] [data-testid="stButton"] button [data-testid="stMarkdownContainer"] {
    flex:1;min-width:0;
}
[class*="st-key-"][class*="_suggestions"] [data-testid="stButton"] button p {
    font-size:12px;line-height:1.55;white-space:normal;text-align:left;margin:0;color:var(--ocop-text-muted);
}
[class*="st-key-"][class*="_suggestions"] [data-testid="stButton"] button p + p {margin-top:5px;}
[class*="st-key-"][class*="_suggestions"] [data-testid="stButton"] button strong {
    font-size:14px;font-weight:750;color:#164c38;
}
@media(hover:hover) {
    [class*="st-key-"][class*="_suggestions"] [data-testid="stButton"] button:not(:disabled):hover {
        background:#edf7ef!important;border-color:#79ad89!important;color:#164c38!important;
        box-shadow:0 5px 14px rgba(18,62,43,.1);transform:translateY(-2px);
    }
    [class*="st-key-"][class*="_suggestions"] [data-testid="stButton"] button:hover p {color:#164c38!important;}
}
@container(max-width:640px) {
    [data-testid="stHorizontalBlock"]:has([class*="_suggestion_"]) {grid-template-columns:minmax(0,1fr)!important;}
    [class*="_suggestion_"] button {height:auto!important;min-height:72px!important;padding:14px!important;}
}
.chat-products {container-type:inline-size;}
.chat-suggestions-heading {
    display:flex;align-items:center;gap:8px;margin:6px 0 2px;
    font-size:15px;font-weight:750;line-height:1.5;color:#123e2b;
}
.chat-suggestions-heading::before {content:'';width:4px;height:18px;border-radius:3px;background:#287a4d;}
[class*="_followup_chips"],
[class*="_followup_chips"] > [data-testid="stVerticalBlock"] {
    display:flex!important;flex-direction:row!important;flex-wrap:wrap!important;
    gap:8px!important;align-items:center!important;
}
[class*="_followup_chips"] [data-testid="stElementContainer"] {
    width:fit-content!important;max-width:100%;flex:0 1 auto;
}
[class*="st-key-"][class*="_suggestions"] [class*="_followup_chips"] [data-testid="stButton"] button {
    width:auto!important;max-width:100%;height:auto!important;min-height:40px!important;
    padding:8px 13px!important;gap:7px;align-items:center;border-radius:999px;
    border:1px solid #b9d3c2;background:#eef6f0;color:#195b3e;
    box-shadow:none;
}
[class*="st-key-"][class*="_suggestions"] [class*="_followup_chips"] [data-testid="stButton"] button p {
    font-size:13px;font-weight:600;line-height:1.5;color:#195b3e;
}
@media(hover:hover) {
    [class*="st-key-"][class*="_suggestions"] [class*="_followup_chips"] [data-testid="stButton"] button:not(:disabled):hover {
        background:#195b3e!important;border-color:#195b3e!important;color:var(--ocop-text-on-accent)!important;
        box-shadow:0 3px 8px rgba(25,91,62,.15);transform:translateY(-1px);
    }
    [class*="st-key-"][class*="_suggestions"] [class*="_followup_chips"] [data-testid="stButton"] button:hover p {color:var(--ocop-text-on-accent)!important;}
}
.chat-products-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;}
.chat-product {display:flex;flex-direction:column;min-width:0;}
.chat-products .product-card {border:1px solid #e5ebe3;border-radius:14px;overflow:hidden;background:var(--ocop-surface-product);margin-bottom:0;flex:1;}
.chat-products .product-photo {width:100%;height:172px;object-fit:contain;background:var(--ocop-surface-product);display:block;padding:12px;box-sizing:border-box;border-bottom:1px solid #f0f0f0;}
.product-photo-placeholder,.chat-products .product-photo-placeholder {display:grid;place-items:center;}
.chat-products .product-card-body {padding:13px 14px 14px;display:flex;flex-direction:column;gap:8px;}
.chat-products .product-category {height:30px;line-height:15px;font-size:12px;letter-spacing:.5px;color:var(--ocop-text-accent);font-weight:800;text-transform:uppercase;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;}
.chat-products .product-name {height:80.6px;min-height:0;margin:0;font-size:13px;font-weight:800;color:var(--ocop-text-product);line-height:1.55;overflow:hidden;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow-wrap:anywhere;}
.chat-products .product-meta {height:38px;font-size:12px;color:var(--ocop-text-muted);display:flex;align-items:center;flex-wrap:wrap;gap:4px 8px;line-height:17px;overflow:hidden;}
.chat-products .star-chip {display:inline-block;flex-shrink:0;white-space:nowrap;background:#fff4d9;color:#805500;font-weight:700;padding:4px 7px;border-radius:5px;font-size:12px;}
.chat-products .star-chip-0 {background:#f1f3f5;color:#596579;}
.chat-products .star-chip-4 {background:#e8f5ec;color:#216e39;}
.chat-products .star-chip-5 {background:#fdebec;color:#b42332;}
.chat-products .product-price {height:27px;line-height:27px;margin:0;font-size:18px;color:#c62828;font-weight:800;white-space:nowrap;}
.chat-products .source-chip {height:24px;display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:#59665e;}
.chat-products .source-logo {width:28px;height:20px;object-fit:contain;flex-shrink:0;}
.chat-products .source-name {overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
[data-testid="stMarkdownContainer"] a.chat-product-link {
    display:flex;align-items:center;justify-content:center;min-height:40px;margin-top:8px;padding:8px 12px;
    box-sizing:border-box;border:1px solid #bfd3c4;border-radius:9px;background:#fff;
    color:#195b3e;font-size:13px;font-weight:650;text-decoration:none;
}
:is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a),
[data-testid="stChatInputSubmitButton"],a.chat-product-link,.product-card {
    transition:background-color .18s ease,border-color .18s ease,color .18s ease,box-shadow .18s ease,transform .18s ease;
}
@media(hover:hover) {
    :is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):not(:disabled):hover,
    [data-testid="stMarkdownContainer"] a.chat-product-link:hover {
        background:#195b3e!important;border-color:#195b3e!important;color:var(--ocop-text-on-accent)!important;
        box-shadow:0 4px 10px rgba(25,91,62,.2);transform:translateY(-1px);
    }
    :is([data-testid="stButton"],[data-testid="stLinkButton"]) :is(button,a)[kind="primary"]:not(:disabled):hover {background:#103f2a!important;border-color:#103f2a!important;}
    :is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):not(:disabled):hover p {color:inherit!important;}
    [data-testid="stChatInputSubmitButton"]:not(:disabled):hover {background:#195b3e!important;color:var(--ocop-text-on-accent)!important;border-radius:8px;}
    .product-card:hover {border-color:#a6c9b0;box-shadow:0 5px 16px rgba(18,62,43,.1);}
}
:is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):focus-visible,
[data-testid="stChatInputSubmitButton"]:focus-visible,a.chat-product-link:focus-visible {
    outline:3px solid #287a4d!important;outline-offset:3px;
}
:is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a):not(:disabled):active,
a.chat-product-link:active {transform:translateY(0);box-shadow:none;}
@container(max-width:420px) {.chat-products-grid{grid-template-columns:minmax(0,1fr);}}
@media(max-width:480px) {
    [data-testid="stChatMessage"]{padding:12px;gap:8px;}
    .chat-products-grid{grid-template-columns:minmax(0,1fr);}
}
@media(prefers-reduced-motion:reduce) {
    :is([data-testid="stButton"],[data-testid="stLinkButton"],[data-testid="stPopoverButton"]) :is(button,a),
    [data-testid="stChatInputSubmitButton"],a.chat-product-link,.product-card {transition:none!important;transform:none!important;}
}
</style>"""
