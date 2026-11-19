"""Chat-only layout and presentation; composed by src.styles."""

CHAT_CSS = """
[data-testid="stChatMessage"] {border-radius:16px;padding:18px;gap:12px;min-width:0;}
[data-testid="stChatMessage"]:has(.ocop-assistant-label) {
    background:#f0f8f2;border:1px solid #cce3d2;border-left:4px solid #287a4d;
    box-shadow:0 3px 12px rgba(18,62,43,.06);
}
[data-testid="stChatMessage"]:has(.ocop-user-label) {background:#f5f6f8;border:1px solid #e7e9ed;}
[data-testid="stChatMessageContent"] {min-width:0;width:100%;}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {line-height:1.6;color:#163d2b;}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {line-height:1.55;margin-bottom:4px;color:#163d2b;}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong {color:#145a37;}
.ocop-assistant-label,.ocop-user-label {font-size:13px;font-weight:800;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;}
.ocop-assistant-label {color:#216b43;}
.ocop-user-label {color:#637185;}
.chat-products-heading {font-size:13px;font-weight:750;color:#234d36;margin:18px 0 10px;}
[class*="st-key-chat_result_"] {background:#fff;border-color:#dce9df!important;border-radius:12px!important;padding:10px!important;}
[class*="st-key-chat_result_"] > [data-testid="stVerticalBlock"] {gap:8px!important;}
.chat-result-summary {display:flex;align-items:center;gap:12px;min-width:0;}
.chat-result-image {width:76px;height:76px;flex:0 0 76px;object-fit:contain;border-radius:8px;background:#f5f8f4;}
.chat-result-placeholder {display:grid;place-items:center;font-size:24px;}
.chat-result-body {min-width:0;display:flex;flex-direction:column;gap:3px;}
.chat-result-name {font-size:14px;font-weight:750;line-height:1.4;color:#123e2b;overflow-wrap:anywhere;}
.chat-result-meta {font-size:13px;line-height:1.4;color:#576b60;}
.chat-result-price {font-size:15px;line-height:1.4;font-weight:800;color:#be3030;}
[class*="st-key-chat_result_"] [data-testid="stHorizontalBlock"] {gap:6px!important;}
[class*="st-key-chat_result_"] [data-testid="stButton"] button,
[class*="st-key-chat_result_"] [data-testid="stLinkButton"] a {min-height:36px;padding:5px 8px;font-size:13px;}
[class*="st-key-chat_result_"] [data-testid="stButton"] button p,
[class*="st-key-chat_result_"] [data-testid="stLinkButton"] a p {font-size:13px;line-height:1.3;}
@media(max-width:600px) {
    [class*="st-key-chat_result_"] [data-testid="stHorizontalBlock"] {flex-wrap:wrap!important;}
    [class*="st-key-chat_result_"] [data-testid="stColumn"] {flex:1 1 135px!important;min-width:0!important;}
    .chat-result-image {width:60px;height:60px;flex-basis:60px;}
}
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
    font-size:13px;line-height:1.55;white-space:normal;text-align:left;margin:0;color:var(--ocop-text-muted);
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
[data-testid="stMarkdownContainer"] a.chat-product-link {
    display:flex;align-items:center;justify-content:center;min-height:40px;margin-top:8px;padding:8px 12px;
    box-sizing:border-box;border:1px solid #bfd3c4;border-radius:9px;background:#fff;
    color:#195b3e;font-size:13px;font-weight:650;text-decoration:none;
}
@container(max-width:420px) {.chat-products-grid{grid-template-columns:minmax(0,1fr);}}
@media(max-width:480px) {
    [data-testid="stChatMessage"]{padding:12px;gap:8px;}
    .chat-products-grid{grid-template-columns:minmax(0,1fr);}
}

    .st-key-floating_chat {
        position:fixed;bottom:calc(96px + env(safe-area-inset-bottom, 0px));
        right:calc(24px + env(safe-area-inset-right, 0px));
        width:auto;max-width:calc(100vw - 48px);z-index:990;
    }
    .st-key-floating_chat [data-testid="stPopoverButton"] > button,
    .st-key-floating_chat button[data-testid="stPopoverButton"],
    .st-key-floating_chat [data-testid="stPopover"] > button {
        border-radius:24px;background:#195b3e;color:#fff;border:1px solid #195b3e;
        padding:10px 18px;min-height:46px;font-weight:700;
        box-shadow:0 5px 18px rgba(18,62,43,.22);
    }
    .st-key-floating_chat [data-testid="stPopoverButton"] > button:hover,
    .st-key-floating_chat button[data-testid="stPopoverButton"]:hover,
    .st-key-floating_chat [data-testid="stPopover"] > button:hover {background:#103f2a!important;}
    @media(max-width:640px){
        .st-key-floating_chat {
            bottom:calc(88px + env(safe-area-inset-bottom, 0px));
            right:calc(16px + env(safe-area-inset-right, 0px));
            max-width:calc(100vw - 32px);
        }
    }

.chat-products .product-card {margin-bottom:0;flex:1;}
"""
