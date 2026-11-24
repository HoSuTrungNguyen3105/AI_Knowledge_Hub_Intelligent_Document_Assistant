#!/usr/bin/env python3
"""Generate workflow 08 — Scheduled Research Digest — as importable n8n JSON.

A small automation that shows what n8n is for beyond webhooks: a Schedule
Trigger runs a research brief on a weekly cadence with no human clicking
anything, one LLM call (Groq preferred, Ollama fallback — whichever key
exists in the n8n env) writes a short Vietnamese digest, and the digest is
sent to Telegram when TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are configured.
Every execution (and its digest) stays visible under n8n -> Executions.

No key value ever appears in the JSON: provider and Telegram credentials
are read from $env at runtime, exactly like workflow 07.
"""
import json
import os
import uuid

OUT = os.environ.get("FACTORY_OUT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "workflows")


def node(name, ntype, type_version, parameters, x, y, **extra):
    n = {"parameters": parameters, "id": str(uuid.uuid4()), "name": name,
         "type": ntype, "typeVersion": type_version, "position": [x, y]}
    n.update(extra)
    return n


def code(name, js, x, y):
    return node(name, "n8n-nodes-base.code", 2,
                {"mode": "runOnceForAllItems", "jsCode": js}, x, y)


def http(name, x, y):
    return node(name, "n8n-nodes-base.httpRequest", 4.2,
                {"method": "POST", "url": "={{ $json.api_url }}",
                 "sendHeaders": True,
                 "headerParameters": {"parameters": [
                     {"name": "Authorization", "value": "={{ $json.auth_header }}"},
                     {"name": "Content-Type", "value": "application/json"}]},
                 "sendBody": True, "contentType": "json", "specifyBody": "json",
                 "jsonBody": "={{ JSON.stringify($json.provider_body) }}",
                 "options": {"timeout": 600000}},
                x, y, retryOnFail=True, maxTries=2, waitBetweenTries=5000,
                onError="continueRegularOutput")


def if_node(name, json_key, x, y):
    return node(name, "n8n-nodes-base.if", 2.2,
                {"conditions": {"options": {"caseSensitive": True, "leftValue": "",
                                            "typeValidation": "loose", "version": 2},
                                "conditions": [{"id": "c1", "leftValue": f"={{{{ ${json_key} }}}}",
                                                "rightValue": True,
                                                "operator": {"type": "boolean", "operation": "true",
                                                             "singleValue": True}}],
                                "combinator": "and"},
                 "options": {}}, x, y)


def chain(workflow, *names):
    for a, b in zip(names, names[1:]):
        workflow["connections"].setdefault(a, {"main": [[]]})
        workflow["connections"][a]["main"][0].append(
            {"node": b, "type": "main", "index": 0})


def connect(workflow, src, dst, output_index=0):
    entry = workflow["connections"].setdefault(src, {"main": [[]]})
    while len(entry["main"]) <= output_index:
        entry["main"].append([])
    entry["main"][output_index].append({"node": dst, "type": "main", "index": 0})


def sticky(text, x, y, width=680, height=300):
    return {"parameters": {"content": text, "height": height, "width": width},
            "id": str(uuid.uuid4()), "name": "Sticky Note",
            "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
            "position": [x, y]}


BRIEF_JS = r"""
// EDIT ME: the standing research topic for the digest. Change the day/hour
// in the Schedule Trigger node to change the cadence.
const TOPIC = 'xu hướng công nghệ giáo dục (EdTech) cho học sinh tiểu học';
const groqKey = $env.GROQ_API_KEY || '';
const ollamaKey = $env.OLLAMA_API_KEY || '';
let provider = null;
if (groqKey) {
  provider = {
    api_url: 'https://api.groq.com/openai/v1/chat/completions',
    auth_header: 'Bearer ' + groqKey,
    model: 'openai/gpt-oss-120b'
  };
} else if (ollamaKey) {
  provider = {
    api_url: 'https://ollama.com/v1/chat/completions',
    auth_header: 'Bearer ' + ollamaKey,
    model: 'gpt-oss:120b'
  };
}
if (!provider) return [{ json: { provider_configured: false } }];
const today = new Date().toISOString().slice(0, 10);
const systemPrompt = 'Bạn là AI Researcher của một đội ngũ giáo dục. Viết ngắn gọn, cụ thể, bằng tiếng Việt, không nói chung chung.';
const userContent = [
  'Hôm nay là ' + today + '. Hãy viết bản tin nghiên cứu tuần về: ' + TOPIC + '.',
  'Cấu trúc bắt buộc:',
  '- Một dòng mở đầu tóm tắt tuần này có gì đáng chú ý.',
  '- Đúng 5 xu hướng/ý tưởng, mỗi mục gồm: tiêu đề in đậm, 3-4 câu mô tả, một câu "Vì sao quan trọng" và một câu "Áp dụng vào lớp học" với ví dụ cụ thể cho giáo viên tiểu học.',
  '- Một mục cuối: "Một việc nên thử tuần này" — một hoạt động nhỏ, làm được ngay.',
  'Chỉ dùng kiến thức chắc chắn, không bịa số liệu hay tên sản phẩm không có thật.'
].join('\n');
return [{ json: {
  provider_configured: true,
  topic: TOPIC,
  api_url: provider.api_url,
  auth_header: provider.auth_header,
  provider_body: {
    model: provider.model,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userContent }
    ],
    max_tokens: 4096,
    temperature: 0.4
  }
} }];
"""

FORMAT_JS = r"""
const input = $input.first().json || {};
let text = '';
const choice = input.choices && input.choices[0];
if (choice && choice.message && typeof choice.message.content === 'string') {
  text = choice.message.content;
} else if (typeof input.response === 'string') {
  text = input.response;
}
const today = new Date().toISOString().slice(0, 10);
const digest = text.trim()
  || '(Không nhận được nội dung từ model — xem chi tiết ở node Research Call.)';
const token = $env.TELEGRAM_BOT_TOKEN || '';
const chatId = $env.TELEGRAM_CHAT_ID || '';
const configured = Boolean(token && chatId);
const full = 'Bản tin nghiên cứu tuần — ' + today + '\n\n' + digest;
return [{ json: {
  digest_text: digest,
  telegram_configured: configured,
  api_url: configured ? 'https://api.telegram.org/bot' + token + '/sendMessage' : '',
  auth_header: '',
  provider_body: { chat_id: chatId, text: full.slice(0, 3900) }
} }];
"""


def workflow_eight_scheduled_digest():
    wf = {"name": "AI Factory — Scheduled Research Digest",
          "nodes": [], "connections": {},
          "settings": {"saveDataErrorExecution": "all", "saveDataSuccessExecution": "all",
                       "saveManualExecutions": True, "executionOrder": "v1"},
          "staticData": None, "pinData": {}}
    add = wf["nodes"].append
    add(sticky("## Scheduled Research Digest (automation mẫu của n8n)\n"
               "Chạy **tự động mỗi tuần** (mặc định thứ 2, 07:00 — sửa trong node Schedule Trigger): "
               "AI Researcher viết bản tin ngắn về xu hướng EdTech cho học sinh tiểu học rồi gửi qua "
               "Telegram. Không cần ai bấm chạy và không phụ thuộc MindFlow có đang mở hay không.\n\n"
               "- Chủ đề đứng: sửa hằng số `TOPIC` trong node **Build Research Brief**.\n"
               "- Model: ưu tiên Groq `gpt-oss-120b`, thiếu key Groq thì dùng Ollama `gpt-oss:120b` "
               "(key đọc từ $env như workflow 07).\n"
               "- Telegram chỉ gửi khi có `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` trong .env; "
               "chưa cấu hình thì bản tin vẫn nằm trong chi tiết execution (node Format Digest).\n"
               "- Workflow chỉ chạy theo lịch khi đang **Active**; bấm Execute Workflow để chạy thử ngay.", -80, 60))
    add(node("Weekly Schedule", "n8n-nodes-base.scheduleTrigger", 1.2,
             {"rule": {"interval": [{"field": "weeks", "weeksInterval": 1,
                                     "triggerAtDay": [1], "triggerAtHour": 7,
                                     "triggerAtMinute": 0}]}},
             0, 300))
    add(code("Build Research Brief", BRIEF_JS, 260, 300))
    add(if_node("Provider Configured", "json.provider_configured", 520, 300))
    add(http("Research Call", 780, 300))
    add(code("Format Digest", FORMAT_JS, 1040, 300))
    add(if_node("Telegram Configured", "json.telegram_configured", 1300, 300))
    add(http("Notify Telegram", 1560, 300))

    chain(wf, "Weekly Schedule", "Build Research Brief", "Provider Configured")
    connect(wf, "Provider Configured", "Research Call", output_index=0)
    chain(wf, "Research Call", "Format Digest", "Telegram Configured")
    connect(wf, "Telegram Configured", "Notify Telegram", output_index=0)
    return wf


def main():
    os.makedirs(OUT, exist_ok=True)
    wf = workflow_eight_scheduled_digest()
    path = os.path.join(OUT, "08-scheduled-research-digest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"wrote {os.path.basename(path)}: {len(wf['nodes'])} nodes")


if __name__ == "__main__":
    main()
