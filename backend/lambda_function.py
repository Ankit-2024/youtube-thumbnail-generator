import json
import boto3
import base64
import os
import io
import textwrap
from PIL import Image, ImageDraw, ImageFont

# ── Clients ──────────────────────────────────────────────────────────────────
bedrock = boto3.client("bedrock-runtime")
s3_client = boto3.client("s3")

# ── Config (set these as Lambda environment variables) ────────────────────────
BUCKET_NAME = os.environ["THUMBNAIL_BUCKET"]       # e.g. "my-thumbnails-bucket"
FONT_PATH   = os.path.join(os.path.dirname(__file__), "BebasNeue-Regular.ttf")


# ── Entry point ───────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return _response(200, {})

    try:
        body = json.loads(event.get("body") or "{}")
        video_idea = (body.get("video_idea") or "").strip()

        if not video_idea:
            return _response(400, {"error": "video_idea is required"})

        # 1. Generate title + image prompt via Claude Haiku
        title, image_prompt = _generate_text(video_idea)

        # 2. Generate background image via Titan
        image_bytes = _generate_image(image_prompt)

        # 3. Composite title text onto the image using Pillow
        final_jpeg = _composite_thumbnail(image_bytes, title)

        # 4. Upload to S3
        key = f"thumbnails/{context.aws_request_id}.jpg"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=final_jpeg,
            ContentType="image/jpeg",
        )

        # 5. Return a presigned download URL (valid 24 hours)
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=86400,
        )

        return _response(200, {"url": url, "title": title})

    except bedrock.exceptions.ValidationException as e:
        return _response(400, {"error": f"Bedrock validation error: {str(e)}"})
    except Exception as e:
        print(f"Unhandled error: {e}")
        return _response(500, {"error": "Internal server error"})


# ── Step 1: Text generation (Claude Haiku) ────────────────────────────────────

def _generate_text(video_idea: str) -> tuple[str, str]:
    """
    Calls Claude Haiku to produce:
      - title       : punchy ALL-CAPS YouTube thumbnail title (≤ 6 words)
      - image_prompt: detailed Stable-Diffusion-style prompt for Titan
    Returns (title, image_prompt).
    """
    prompt = f"""You are a YouTube thumbnail designer.
Given a video idea, return ONLY a valid JSON object with two keys:
  "title"        — a punchy thumbnail title, ALL CAPS, maximum 6 words
  "image_prompt" — a detailed cinematic image generation prompt (no text/logos in scene)

Example output:
{{"title": "PYTHON TIPS YOU NEED", "image_prompt": "cinematic wide shot of a glowing laptop on a dark desk, code on screen, dramatic side lighting, 4k"}}

Video idea: {video_idea}"""

    resp = bedrock.invoke_model(
        modelId="global.anthropic.claude-haiku-4-5-20251001-v1:0",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )

    raw = json.loads(resp["body"].read())
    text = raw["content"][0]["text"].strip()

    # Strip markdown code fences if Claude wraps in ```json ... ```
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    parsed = json.loads(text)
    return parsed["title"], parsed["image_prompt"]


# ── Step 2: Image generation (Titan Image Generator) ─────────────────────────

def _generate_image(image_prompt: str) -> bytes:
    resp = bedrock.invoke_model(
        modelId="stability.sd3-5-large-v1:0",
        body=json.dumps({
            "prompt": image_prompt,
            "mode": "text-to-image",
            "aspect_ratio": "16:9",
            "output_format": "jpeg",
            "seed": 42,
        }),
    )
    result = json.loads(resp["body"].read())
    return base64.b64decode(result["images"][0])



# ── Step 3: Pillow composite ──────────────────────────────────────────────────

def _composite_thumbnail(image_bytes: bytes, title: str) -> bytes:
    """
    Composites a bold title onto the generated image:
      - dark gradient overlay at the bottom third
      - white title text with a drop shadow
      - returns final JPEG bytes
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    img = img.resize((1280, 720), Image.LANCZOS)

    # ── Gradient overlay (dark bar at bottom for text legibility) ──
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    gradient_height = 320
    for i in range(gradient_height):
        alpha = int((i / gradient_height) ** 1.5 * 210)   # ease-in curve
        y = 720 - gradient_height + i
        draw_overlay.rectangle([(0, y), (1280, y + 1)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    # ── Font ──────────────────────────────────────────────────────
    # Large font for title, smaller for "by <channel>" if you extend later
    try:
        font_title = ImageFont.truetype(FONT_PATH, 100)
        font_sub   = ImageFont.truetype(FONT_PATH, 42)
    except IOError:
        # Fallback: Pillow default (no custom font needed, but won't look as good)
        print("WARNING: BebasNeue-Regular.ttf not found — using default font")
        font_title = ImageFont.load_default()
        font_sub   = ImageFont.load_default()

    # ── Wrap title to max 18 chars per line ───────────────────────
    lines = textwrap.wrap(title, width=18)

    LINE_HEIGHT = 108
    MARGIN_LEFT = 48
    MARGIN_BOTTOM = 48

    total_text_height = len(lines) * LINE_HEIGHT
    y_start = 720 - total_text_height - MARGIN_BOTTOM

    for line in lines:
        # Shadow (offset 4px down-right, semi-transparent black)
        draw.text((MARGIN_LEFT + 4, y_start + 4), line,
                  font=font_title, fill=(0, 0, 0, 180))
        # Main white text
        draw.text((MARGIN_LEFT, y_start), line,
                  font=font_title, fill=(255, 255, 255, 255))
        y_start += LINE_HEIGHT

    # ── Save as JPEG ──────────────────────────────────────────────
    final = img.convert("RGB")
    buf = io.BytesIO()
    final.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
        },
        "body": json.dumps(body),
    }
