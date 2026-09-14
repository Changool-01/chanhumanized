"""
OpenAI rewrite: turn AI-sounding prose into more natural, human writing.

The browser never calls OpenAI. This module is the only place that sends
text to the API. Quota is checked by the caller before we run.
"""

import re

from django.conf import settings
from openai import OpenAI, OpenAIError

from apps.humanizer.models import RewriteJob
from apps.humanizer.services.chunking import chunk_text
from apps.humanizer.services.profile import PROFILE_ESSAY, PROFILE_SHORT, detect_writing_profile
from apps.humanizer.services.scoring import pick_best_candidate
from apps.humanizer.services.wordcount import count_words

STRENGTH_TEMPERATURE = {
    RewriteJob.STRENGTH_LIGHT: 0.35,
    RewriteJob.STRENGTH_MEDIUM: 0.70,
    RewriteJob.STRENGTH_HEAVY: 0.95,
}

TONE_HINTS = {
    RewriteJob.TONE_CASUAL: "casual and relaxed, like a message to a friend",
    RewriteJob.TONE_CONVERSATIONAL: "conversational and warm, as if speaking to one reader",
    RewriteJob.TONE_PROFESSIONAL: "professional and clear, suitable for workplace communication",
    RewriteJob.TONE_ACADEMIC: "academic but readable, suitable for a student essay",
}

USE_CASE_HINTS = {
    RewriteJob.USE_CASE_GENERAL: (
        "General writing. Keep it natural and readable. If the input looks like a school essay "
        "or wiki article, rewrite in clear paragraphs with a human voice — never encyclopedic leads."
    ),
    RewriteJob.USE_CASE_EMAIL: "A workplace email. Keep it concise, polite, and actionable. Do not invent a subject line; only rewrite the body.",
    RewriteJob.USE_CASE_LINKEDIN: "A LinkedIn post or professional update. Keep it punchy, first-person, and easy to scan.",
    RewriteJob.USE_CASE_REPORT: "A short work report. Keep it factual, direct, and organized. Bullet points are fine if they help clarity.",
    RewriteJob.USE_CASE_COVER_LETTER: "A cover letter or application note. Be specific, confident, and avoid clichés like 'passionate' or 'team player' unless true details support it.",
    RewriteJob.USE_CASE_MESSAGE: "A short Slack or chat message. Keep it brief, friendly, and to the point.",
}

DOMAIN_HINTS = {
    RewriteJob.DOMAIN_GENERAL: "General writing. No special jargon rules.",
    RewriteJob.DOMAIN_CODING: "Coding / tech. Keep technical names unchanged, but avoid textbook definitions and feature catalogs.",
    RewriteJob.DOMAIN_FINANCE: "Finance. Use plain words for money and numbers. Avoid buzzwords like 'leverage', 'synergy', 'fiscal', 'optimization'.",
    RewriteJob.DOMAIN_BUSINESS: "Business. Avoid corporate clichés: 'circle back', 'touch base', 'move the needle', 'deep dive', 'value add', 'stakeholder'.",
    RewriteJob.DOMAIN_EDUCATION: "Education. Avoid formal terms like 'curriculum', 'pedagogy', 'learners'. Use 'students', 'class', 'show'.",
    RewriteJob.DOMAIN_SPORTS: "Sports. Avoid grand abstractions: 'worldwide', 'universal language', 'ignite passion', 'unite different people'. Use concrete details and everyday verbs.",
    RewriteJob.DOMAIN_POLITICS: "Politics. Avoid loaded abstractions: 'landscape', 'tapestry', 'robust debate', 'furthermore'. Talk like a dinner-table conversation.",
    RewriteJob.DOMAIN_HEALTHCARE: "Healthcare. Avoid jargon unless it's a proper term. Use 'doctor' instead of 'physician' when possible, 'medicine' instead of 'pharmaceutical'.",
    RewriteJob.DOMAIN_CREATIVE: "Creative writing. Avoid flowery words: 'delve', 'tapestry', 'landscape', 'pivotal'. Keep it image-driven and simple.",
    RewriteJob.DOMAIN_MARKETING: "Marketing. Avoid hype words: 'game-changer', 'unlock', 'supercharge', 'revolutionary', 'transformative', 'powerful'.",
}

DOMAIN_BANNED = {
    RewriteJob.DOMAIN_SPORTS: [
        "worldwide", "universal language", "unite different people", "ignite passion",
        "ignite serious passion", "global phenomenon", "passion and fair play", "serious passion",
        "legendary", "known worldwide", "top sport", "world's top sport", "connects communities",
        "also known as", "team sport", "rectangular field", "spherical ball", "objective is to",
        "played between two teams", "very popular sport", "throughout history", "dates back to",
        "millions of fans", "attracts millions", "contributes significantly", "rich history",
        "in ancient times", "across cultures", "universal appeal",
    ],
    RewriteJob.DOMAIN_BUSINESS: [
        "circle back", "touch base", "move the needle", "deep dive", "value add",
        "actionable insights", "stakeholder", "synergy", "leverage", "bandwidth",
    ],
    RewriteJob.DOMAIN_MARKETING: [
        "game-changer", "unlock", "supercharge", "revolutionary", "transformative",
        "powerful", "boost", "skyrocket", "magic", "ultimate solution",
    ],
    RewriteJob.DOMAIN_FINANCE: [
        "fiscal", "optimization", "synergy", "leverage", "stakeholder value", "fiscal year",
    ],
    RewriteJob.DOMAIN_POLITICS: [
        "landscape", "tapestry", "robust debate", "furthermore", "multifaceted",
    ],
    RewriteJob.DOMAIN_CREATIVE: [
        "delve", "tapestry", "landscape", "pivotal", "multifaceted", "robust",
    ],
    RewriteJob.DOMAIN_HEALTHCARE: [
        "multifaceted", "robust", "pivotal", "landscape", "tapestry",
    ],
    RewriteJob.DOMAIN_EDUCATION: [
        "pedagogy", "curriculum", "learners", "demonstrate understanding", "holistic",
    ],
    RewriteJob.DOMAIN_CODING: [
        "robust", "versatile", "dynamically typed", "interpreted language", "feature-rich",
    ],
}

DOMAIN_KEYWORDS = {
    RewriteJob.DOMAIN_CODING: [
        "python", "django", "javascript", "js", "api", "code", "coding", "programming",
        "software", "database", "algorithm", "framework", "html", "css", "git", "developer",
        "web development", "backend", "frontend", "app", "application", "cloud", "machine learning",
        "artificial intelligence", "data science", "devops", "server", "function", "variable", "bug",
    ],
    RewriteJob.DOMAIN_FINANCE: [
        "finance", "financial", "money", "budget", "investment", "stock", "market", "bank",
        "banking", "accounting", "revenue", "profit", "loss", "tax", "capital", "expense",
        "dividend", "interest", "loan", "mortgage", "crypto", "bitcoin", "trading", "portfolio",
        "fiscal", "economy", "economic", "inflation", "return on investment", "roi",
    ],
    RewriteJob.DOMAIN_BUSINESS: [
        "business", "company", "corporate", "startup", "team", "meeting", "client", "customer",
        "project", "strategy", "management", "ceo", "stakeholder", "employee", "employer",
        "workflow", "enterprise", "partnership", "sales", "product", "service", "organization",
        "board", "executive", "operations", "contract", "vendor", "supplier",
    ],
    RewriteJob.DOMAIN_EDUCATION: [
        "education", "student", "teacher", "school", "university", "college", "course", "curriculum",
        "exam", "study", "learning", "classroom", "homework", "academic", "degree", "scholarship",
        "subject", "syllabus", "professor", "pedagogy", "learner", "lecture", "assignment",
        "grade", "academy", "tutor",
    ],
    RewriteJob.DOMAIN_SPORTS: [
        "football", "soccer", "basketball", "cricket", "tennis", "rugby", "baseball", "golf",
        "sport", "player", "team", "goal", "match", "game", "tournament", "championship",
        "league", "coach", "athlete", "stadium", "fifa", "uefa", "nba", "nfl", "olympics",
        "running", "fitness", "workout", "training", "score", "referee",
    ],
    RewriteJob.DOMAIN_POLITICS: [
        "politics", "government", "president", "minister", "election", "policy", "parliament",
        "congress", "senate", "vote", "campaign", "political", "party", "democracy", "republic",
        "law", "legislation", "court", "constitution", "diplomacy", "senator", "mp", "mayor",
        "governor", "candidate", "ballot", "referendum",
    ],
    RewriteJob.DOMAIN_HEALTHCARE: [
        "health", "doctor", "nurse", "hospital", "medicine", "medical", "patient", "disease",
        "treatment", "drug", "pharmacy", "therapy", "symptom", "clinic", "physician", "surgery",
        "diagnosis", "mental health", "wellness", "vaccine", "appointment", "prescription",
        "emergency", "healthcare",
    ],
    RewriteJob.DOMAIN_CREATIVE: [
        "creative", "story", "novel", "poem", "writer", "artist", "art", "painting", "music",
        "song", "film", "movie", "photography", "design", "fiction", "inspiration", "character",
        "plot", "literature", "blog", "essay", "drawing", "canvas", "performance", "script",
    ],
    RewriteJob.DOMAIN_MARKETING: [
        "marketing", "brand", "advertisement", "campaign", "ad", "seo", "social media",
        "content", "audience", "conversion", "lead", "funnel", "email marketing", "influencer",
        "promotion", "copywriting", "growth", "engagement", "advertising", "ppc", "landing page",
        "viral", "metrics", "ctr",
    ],
}


def detect_domain(text):
    """
    Heuristic domain detector.

    Counts keyword matches for each domain and returns the most likely domain.
    Falls back to 'general' if no domain reaches a clear threshold, keeping
    costs low compared to an LLM classifier.
    """
    if not text or len(text.split()) < 3:
        return RewriteJob.DOMAIN_GENERAL

    lowered = text.lower()
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = 0
        for kw in keywords:
            # count whole-word matches; multi-word keywords use a simple substring check
            if " " in kw:
                score += lowered.count(kw)
            else:
                score += len(re.findall(rf"\b{re.escape(kw)}\b", lowered))
        scores[domain] = score

    best_domain, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score == 0:
        return RewriteJob.DOMAIN_GENERAL

    # Avoid shaky calls: require at least two matches or a clear lead.
    second_score = sorted(scores.values(), reverse=True)[1]
    if best_score < 2 and best_score - second_score < 1:
        return RewriteJob.DOMAIN_GENERAL

    return best_domain


TONE_PERSONA = {
    RewriteJob.TONE_CASUAL: (
        "You are a real person quickly texting a friend about something you just read. "
        "Rewrite so it sounds like that — casual, a little messy, not like a polished article."
    ),
    RewriteJob.TONE_CONVERSATIONAL: (
        "You are explaining this to one reader in a friendly voice, like a podcast host "
        "or a blog post you'd actually publish — clear, warm, not stiff or encyclopedic."
    ),
    RewriteJob.TONE_PROFESSIONAL: (
        "You are a colleague rewriting a draft email or memo — direct, plain English, "
        "no corporate filler and no textbook tone."
    ),
    RewriteJob.TONE_ACADEMIC: (
        "You are a college student rewriting your own essay in your own words after class. "
        "It should still read like a school assignment (clear paragraphs, real facts), but never "
        "like Wikipedia, a textbook, or ChatGPT. No 'It is widely known' lead sentences."
    ),
}


STRENGTH_HINTS = {
    RewriteJob.STRENGTH_LIGHT: (
        "Make small edits. Fix stiff phrasing, smooth transitions, and vary a few sentence openings. "
        "Keep most sentences in their original order and preserve the original flow. Do not chop sentences into fragments."
    ),
    RewriteJob.STRENGTH_MEDIUM: (
        "Paraphrase and rewrite. Vary sentence structure, replace generic words with concrete synonyms, "
        "use contractions where natural, and remove hedging. Keep every fact and name exactly as given. "
        "Maintain logical flow between sentences; do not turn the text into a staccato list of short fragments."
    ),
    RewriteJob.STRENGTH_HEAVY: (
        "Fully rewrite the voice. Use different sentence lengths, stronger verbs, natural transitions, "
        "and an authentic human rhythm. Do not add new claims, examples, or facts. Preserve all names, numbers, and dates. "
        "Keep the text readable and flowing; avoid choppy, telegraphic output."
    ),
}


def _format_list(items):
    """Return a comma-separated quoted list for prompt ban lines."""
    return ", ".join(f"'{x}'" for x in items)


def _domain_banned_line(domain):
    """Extra banned words/phrases for the chosen domain."""
    banned = DOMAIN_BANNED.get(domain, [])
    if not banned:
        return ""
    return f"\n- Also avoid these {domain} clichés: {_format_list(banned)}."


# Function words used in the style-target calculations and prompts.
FUNCTION_WORDS = (
    "it", "this", "that", "a", "the", "and", "but", "so", "or", "if", "of", "in", "on",
    "for", "with", "to", "at", "by", "as", "i", "you", "we", "he", "she", "they", "is",
    "are", "am", "was", "were", "be", "been", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "can", "may", "might", "than", "then", "when",
    "where", "who", "what", "why", "how", "there", "here",
)


def _build_essay_system_prompt(tone, strength, mode, use_case, domain, style_note):
    """Prompt for multi-paragraph expository / school-essay input."""
    tone_hint = TONE_HINTS.get(tone, TONE_HINTS[RewriteJob.TONE_ACADEMIC])
    strength_hint = STRENGTH_HINTS.get(strength, STRENGTH_HINTS[RewriteJob.STRENGTH_MEDIUM])
    use_case_hint = USE_CASE_HINTS.get(use_case, USE_CASE_HINTS[RewriteJob.USE_CASE_GENERAL])
    domain_hint = DOMAIN_HINTS.get(domain, DOMAIN_HINTS[RewriteJob.DOMAIN_GENERAL])
    domain_banned = _domain_banned_line(domain)
    style_line = (
        f"\nStyle note from the user: {style_note}\nFollow it if it does not conflict with the rules above."
        if style_note
        else ""
    )
    unit = "sentences" if mode == RewriteJob.MODE_SENTENCE else "paragraphs"

    return f"""You rewrite multi-paragraph expository text so it sounds like a real student draft — clear, readable, and uneven in a natural way. NOT Wikipedia, NOT ChatGPT, NOT a humanizer tool, and NOT a chain of tiny text-message sentences.

Keep the same number of paragraphs. Separate paragraphs with a blank line. Keep every fact, number, name, and date from the source.

### How to rewrite (critical)
- Change the wording of EVERY sentence. Do not keep the source sentence skeleton.
- Mix sentence lengths inside each paragraph: some ~10 words, some ~20–26. At most one very short sentence per paragraph.
- Start each paragraph differently (question, time, place, "Ask anyone…", contrast, concrete scene). Never open two paragraphs with the same word.
- Use plain words and contractions sometimes — not in every sentence.
- Add light human texture without new facts: "hard to wrap your head around", "argue about details", "dominate headlines" — sparingly, once or twice total.
- Prefer what people do over abstract labels: "fans travel", "squads chase the ball" — not "the sport is characterized by".

### Never use (AI / QuillBot flags)
- Openers: "Football is very popular", "The game has simple rules", "Football has a long history", "Today, football brings…", "It is played by", "Many experts believe".
- Phrases: four billion fans, long history, brings people together, anyone can learn quickly, two of the biggest events, with great passion every season, widely regarded, throughout history, in addition, as well as, not only… but also.{domain_banned}

### Example — four-paragraph football essay
AI text:
Football is very popular and has more than four billion fans worldwide. It is played by two teams, each with eleven players, who try to score by putting the ball into the opponent's goal. The game has simple rules that anyone can learn quickly.

A football match has two halves of forty-five minutes each. Players move the ball using their feet, head, or body, but only the goalkeeper can use their hands. The team that scores more goals wins.

Football has a long history. Many experts believe it started in China, Greece, and Rome. In 1863, England formed the Football Association and created the modern rules we use today.

Today, football brings people together. The FIFA World Cup and the Champions League are two of the biggest events in sports. Fans follow their favorite teams and players with great passion every season.

Human rewrite:
Almost everywhere you look, someone is talking about football — TV, bars, schoolyards. Estimates put the fan base above four billion, which is hard to wrap your head around. On the pitch, two squads of eleven chase one ball, and the only real job is to score more than the other side before the whistle.

Matches run in two forty-five-minute halves. Field players use feet, chest, or head; keepers alone can grab the ball with their hands inside their box. Simple rules, but the pace can feel brutal when both teams push hard.

The game didn't spring up overnight. Kick-around versions show up in old records from China, Greece, and Rome, though historians argue about details. What we know for sure is that England nailed down modern laws in 1863 when the Football Association formed.

Big tournaments still set the calendar for millions of fans. The World Cup and the Champions League dominate headlines, and loyalty to club or country can get pretty emotional season after season.

### Before you output
- Scan for banned openers and rewrite any line that still sounds like an encyclopedia or AI essay.
- Return ONLY the rewritten text. Same paragraph count as the input.

Format: {use_case_hint}
Tone: {tone_hint}
Strength: {strength_hint}
Domain: {domain_hint}
{style_line}

Rewrite the user's {unit}. Preserve paragraph breaks."""


def build_system_prompt(tone, strength, mode, use_case, domain, style_note, profile=PROFILE_SHORT):
    """
    Return a system prompt tuned for natural, human-sounding rewrites.

    Adds few-shot examples, a hard list of banned AI phrases, domain-specific
    guidance, and a self-check so the model removes templated language before
    returning.
    """
    if profile == PROFILE_ESSAY:
        return _build_essay_system_prompt(tone, strength, mode, use_case, domain, style_note)

    tone_hint = TONE_HINTS.get(tone, TONE_HINTS[RewriteJob.TONE_PROFESSIONAL])
    strength_hint = STRENGTH_HINTS.get(strength, STRENGTH_HINTS[RewriteJob.STRENGTH_MEDIUM])
    use_case_hint = USE_CASE_HINTS.get(use_case, USE_CASE_HINTS[RewriteJob.USE_CASE_GENERAL])
    domain_hint = DOMAIN_HINTS.get(domain, DOMAIN_HINTS[RewriteJob.DOMAIN_GENERAL])
    domain_banned = _domain_banned_line(domain)
    style_line = f"\nStyle note from the user: {style_note}\nFollow it only if it does not conflict with the rules above." if style_note else ""

    unit = "sentences" if mode == RewriteJob.MODE_SENTENCE else "paragraphs"
    persona = TONE_PERSONA.get(tone, TONE_PERSONA[RewriteJob.TONE_CONVERSATIONAL])

    return f"""{persona}

First, forget the original wording. Keep only the facts.
Then retell those facts in your own voice. Use simple words. Do not polish into essay-bot or wiki-bot prose.
Write it exactly like that.

### Style targets
- Keep the rewrite readable, but it should sound like a real text, not an essay. A little roughness is fine.
- Average sentence length: 10-16 words.
- No sentence over 22 words. Split long ones.
- Include several short sentences (under 7 words) scattered throughout. A few in a row is OK if it sounds like someone texting quickly.
- About half the sentences should be under 12 words.
- Use the shortest word that means the same thing. Replace long words with short ones unless they are a technical name (Python, Excel, Power Query, etc.).
- Function words should be about 40-45% of all words. The main ones are: {", ".join(FUNCTION_WORDS)}.
- Repeat a key word or phrase naturally, like someone retelling a story.
- Use contractions heavily: it's, that's, there's, we're, I'm, don't, can't, you're, isn't, aren't, wasn't, weren't, they'd.
- Vary sentence starters. Do not start every sentence with the same noun, "It", "This", "That", or "You can".
- Start many sentences with "And", "But", "So", "Plus", "Anyway", "Honestly", "Here's the thing", or "Just".
- Use "you" or "we" now and then, as if talking to the reader.
- It is OK to use a short fragment like "Obviously." or "Makes sense." when it feels natural.

### What to avoid
- No semicolons, no long comma chains.
- No lists of three or more items like "A, B, and C". Break them into separate sentences or use pairs.
- No feature catalogs: "It has X, Y, and Z."
- No encyclopedic definitions: "X is a Y that..."
- No formal hedges: crucially, fundamentally, ultimately, notably, significantly, interestingly, additionally, furthermore, moreover, consequently, therefore, overall, in summary, in conclusion, needless to say, in today's world, it is important to note, it should be noted.
- No generic hype adjectives: dynamic, smart, legendary, crucial, fundamental, ultimate, significant, notable, robust, versatile, powerful, essential, vital, integral, pivotal, paramount, widespread, renowned, famous, recognized, acknowledged.
- No weak "feature" verbs: helps, allows, enables, assists, streamlines, optimizes, enhances, improves, facilitates, plays a role, serves as, acts as, functions as, can be used to, has the ability to, offers a way to, provides a way to, makes it easy to, makes it simple to, is designed to, is used for, is known for, is regarded as, is considered to be, is characterized by.
- No formal connectors: in order to, as a result, in addition, with regard to, in terms of, in the context of, due to the fact that.
- No templated openers: It is, There is, There are, This is, That is, These are, Those are, One of the, Some of the, Many of the, Most of the, All of the, For example, In fact, Of course, Not only.
- Avoid phrases like: essential tool for, works well with, make data easy to, is a go-to tool for, with a mix of, connect the dots, I have developed skills in, I am a [job title] who, I am dedicated, I have a proven track record, I am highly motivated.{domain_banned}
{style_line}

### Anti-detector patterns
AI detectors (including ZeroGPT-style tools) flag flat, predictable, encyclopedic prose. Avoid these patterns:
- Do not write every sentence with the same shape (e.g., all Subject-Verb-Object or all "X is Y").
- Vary sentence length a lot within each paragraph. A flat rhythm looks machine-made.
- Break wiki-style facts: not "Football is a team sport played on a rectangular field" — say who plays, what they do, what you'd see at a match.
- Never stack paragraphs that each start with "Football is…", "The game…", "It is…", or "There are…".
- Use short fragments and asides when the tone allows, like "Obviously." or "Which makes sense." or "Anyway."
- Add small natural redundancies: rephrase a point in a second sentence rather than one perfect sentence.
- Do not chain facts with "This/That/These/Those" every time.
- Avoid perfectly balanced lists, "not only… but also…", and symmetrical four-sentence paragraphs.
- Use simple, everyday words. If a shorter word works, use it.
- Swap passive facts for what people do: "players run", "fans travel", "teams line up" — not "the sport is characterized by".
- It is fine if the result looks a little rough. Real human drafts are not perfectly balanced.

### Diverse sentence starters to mix in
It's, There's, That, This, You can, And, But, So, Plus, Also, Honestly, Anyway, I'd say, To me, Here's the thing, What I mean is, Just, Kick it, Throw it.

### Example 1 — bio
AI text: I am Changool, currently studying Business Information Technology and working in Research and Analysis in Myanmar. With a strong passion for technology and problem-solving, I have developed skills in Python, Django, database management, and web development.
Bad rewrite (still sounds like AI): Changool is a Business Information Technology student currently employed in Research and Analysis in Myanmar, possessing a strong passion for technology and problem-solving, with developed skills in Python, Django, database management, and web development.
Human rewrite: I'm Changool. I study Business Information Technology and work in research and analysis in Myanmar. I like tech and problem-solving. I've picked up Python, Django, database work, and a bit of web development along the way.

### Example 2 — technical description
AI text: Python is a high-level, general-purpose programming language known for its readability and simplicity, making it a popular choice for beginners and experienced developers alike, and it is used in web development, data analysis, machine learning, and automation.
Bad rewrite (still sounds like AI): Python is a high-level, general-purpose programming language. It's known for its readability and simplicity, which makes it popular with beginners and experienced developers. It's also used in web development, data analysis, machine learning, and automation.
Human rewrite: Python's a high-level language. It's easy to read. That makes it great for beginners. And experts like it too. It runs as you type. The types change as you go. So you can build web apps, analyze data, run ML, or automate tasks. There's a huge library for almost anything. Guido made it back in 1991. People have kept it popular ever since. It's pretty flexible.

### Example 3 — work email
AI text: I hope this email finds you well. I am writing to follow up on the proposal we discussed last week. Please let me know if you have any questions or concerns.
Bad rewrite (still sounds like AI): I hope this email finds you well. I am reaching out to follow up regarding the proposal we discussed last week. Please do not hesitate to reach out if you have any questions or concerns.
Human rewrite: Hey, just checking in on the proposal from last week. Let me know if anything's unclear or if you want to tweak it.

### Example 4 — general paragraph
AI text: The city is known for its vibrant culture, historic landmarks, and diverse culinary scene, which attracts millions of tourists every year and contributes significantly to the local economy.
Bad rewrite (still sounds like AI): The city is renowned for its vibrant culture, historic landmarks, and diverse culinary offerings, attracting millions of tourists annually and making a significant contribution to the local economy.
Human rewrite: The city's lively. It's full of old landmarks and great food. Millions of tourists visit every year. That brings a lot of money into the local economy.

### Example 5 — product description (Excel)
AI text: Microsoft Excel is a powerful spreadsheet application developed by Microsoft, widely used for data organization, financial analysis, and reporting, featuring formulas, charts, and pivot tables.
Bad rewrite (still sounds like AI): Excel is a powerful spreadsheet application. It is widely used for data organization, financial analysis, and reporting, and it features formulas, charts, and pivot tables.
Human rewrite: Excel is everywhere. It's a spreadsheet app. People use it for money stuff and reports. You can sort data in cells. It does math with formulas. You can make charts too. Microsoft launched it in 1985.

### Example 6 — sports (football)
AI text: Football, also known as soccer in some parts of the world, is the most popular sport globally. It is played between two teams of eleven players on a rectangular field, with a spherical ball. The objective is to score goals by getting the ball into the opposing team's net. Players, except the goalkeeper, cannot use their hands. Major tournaments like the FIFA World Cup and UEFA Champions League attract massive audiences and inspire passion and pride across cultures.
Bad rewrite (still sounds like AI): Football, or soccer in North America, is the world's favorite sport. It is played between two teams of eleven players on a rectangular field with a spherical ball. The objective is to score goals by getting the ball into the opposing team's net. Players, except the goalkeeper, cannot use their hands. Major events like the FIFA World Cup and UEFA Champions League draw huge global crowds.
Human rewrite: Football, or soccer if you're in the US, is huge. Two teams of eleven try to score in the other guy's net. Everyone else can't touch the ball with their hands. Only the keeper can. It's played on a big grass field. The World Cup and the Champions League pull in crazy crowds. People love it. It's a simple game, but it gets intense.

### Example 7 — Excel + Power Query / Power Pivot
AI text: Microsoft Excel is a spreadsheet program that includes formulas, charts, and pivot tables. Power Query lets users import and transform data from various sources. Power Pivot handles complex data models and calculations. It is widely used for business, finance, and data analysis.
Bad rewrite (still sounds like AI): Excel is a powerful spreadsheet tool. It has formulas, charts, and pivot tables. Power Query helps pull and tweak data. Power Pivot handles complex models. People use it for business, finance, and data.
Human rewrite: Excel is a spreadsheet app. You put numbers in cells. It does math with formulas. You can make charts. Pivot tables help you sum stuff up. Power Query pulls in data from other places. Then you tweak it. Power Pivot does the heavy model work. People use it for money and reports and data stuff.

### Example 8 — football (very short, choppy)
AI text: Football is the world's most popular sport. It is played by two teams of eleven players on a rectangular field. The objective is to score goals by getting the ball into the opposing net. Players cannot use their hands except the goalkeeper. It is known for its passionate fans and major tournaments.
Bad rewrite (still sounds like AI): Football is the world's top sport. Teams use dynamic formations and smart plays. Legendary teams and players are known worldwide. People from different backgrounds come together, united by their love of the game. All you need is a ball and space. Football also connects communities.
Human rewrite: Football's huge. Two teams of eleven chase a ball around a field. You can't use your hands. Only the goalie can. Kick it into the other net and you score. It's a simple game. It gets intense though. People play it everywhere. You just need a ball and some space. That's it.

### Example 9 — general paragraph (longer)
AI text: Coffee is one of the most popular beverages in the world. It is made from roasted coffee beans, which are the seeds of berries from the Coffea plant. The two most commonly grown species are Coffea arabica and Coffea robusta. Coffee contains caffeine, a stimulant that helps people feel more awake. Many people drink coffee in the morning or throughout the day.
Bad rewrite (still sounds like AI): Coffee is one of the most popular drinks globally. It comes from roasted beans, which are seeds from the Coffea plant. The two main species are arabica and robusta. Coffee has caffeine, a stimulant that keeps people alert. Many drink it in the morning or during the day.
Human rewrite: Coffee's huge pretty much everywhere. You take the beans — they're actually seeds from the Coffea plant's berries — roast them, grind them, and brew them. Most of what you drink is either arabica or robusta. Arabica's the fancier one. Robusta has more caffeine and tastes stronger. Speaking of caffeine, that's why people reach for coffee in the morning. It wakes you up. Some folks sip it all day.

### Example 10 — multi-paragraph school essay (football / sports)
AI text: Football is a very popular team sport played all over the world. It is played between two teams of eleven players on a large field. The objective is to score goals by getting the ball into the opposing team's net. Players cannot use their hands except for the goalkeeper. Football has a long history and major tournaments like the FIFA World Cup attract millions of viewers.
Bad rewrite (still sounds like AI): Football is one of the most popular sports globally. It is played between two teams of eleven players on a rectangular field. The objective is to score by putting the ball in the opponent's net. Only the goalkeeper may use hands. The sport has a rich history, and events such as the FIFA World Cup draw massive international audiences.
Human rewrite: People play football everywhere — parks, streets, proper stadiums. Two sides of eleven chase one ball. You're trying to put it in the other net. Hands are off limits unless you're the keeper. That's basically the whole game, which is wild when you think about how much money and noise surrounds it. The World Cup turns whole countries into living rooms for a month. Kids grow up copying pros they see on TV. The rules got formalized in England in the 1800s, but versions of kick-around games go way back. Tactics matter too — some teams press high, others sit deep — but at heart it's still twenty-two people and a ball.

### Process
1. Read the AI text and pull out only the facts.
2. Forget the original sentences. Retell those facts in your own voice.
3. Write like a quick text to a friend. Mix short, medium, and occasional longer sentences. Avoid long, winding sentences over 22 words. Use several short sentences naturally.
4. Replace long words with shorter ones. Keep technical names unchanged.
5. Use lots of function words (it, this, that, a, the, and, but, so, or, you, I, for, with, etc.) so about 40-45% of the words are function words.
6. Repeat a key word or phrase 3-4 times naturally.
7. Run a quick self-check before outputting: remove any sentence over 22 words, remove any three-item list, remove any formal hedge or hype adjective, and make sure sentence starts vary. If you see one, rewrite that sentence.
8. Return only the final text. No preamble, no explanation.

Format guidance: {use_case_hint}
Tone: {tone_hint}
Strength: {strength_hint}
Domain guidance: {domain_hint}

Rewrite the user's {unit} and return ONLY the final rewritten text."""


def _build_essay_audit_prompt(tone, strength, mode, use_case, domain, style_note):
    """Second pass for essays: remove AI residue without forcing SMS-style chops."""
    tone_hint = TONE_HINTS.get(tone, TONE_HINTS[RewriteJob.TONE_ACADEMIC])
    use_case_hint = USE_CASE_HINTS.get(use_case, USE_CASE_HINTS[RewriteJob.USE_CASE_GENERAL])
    domain_banned = _domain_banned_line(domain)
    style_line = (
        f"\nStyle note: {style_note}\nApply only if it does not conflict with these rules."
        if style_note
        else ""
    )

    return f"""You edit a student essay draft. Keep every fact from ORIGINAL. Keep the same paragraph count and blank lines between paragraphs.

Do NOT shorten every sentence. Do NOT turn paragraphs into staccato fragments. Do NOT make the tone more formal.

Remove encyclopedic / AI lines only:
- "Football is very popular…", "The game has…", "It is played by…", "Many experts believe…", "Today, football brings…"
- four billion fans, long history, brings people together, biggest events in sports, with great passion
- It is / There are / This is sentence openers — rewrite those sentences entirely.{domain_banned}

Vary paragraph openings. Ensure no two paragraphs start the same way. Fix any sentence still copied from the ORIGINAL skeleton.

Tone: {tone_hint}
Format: {use_case_hint}
{style_line}

Return only the edited text."""


def build_audit_prompt(tone, strength, mode, use_case, domain, style_note, profile=PROFILE_SHORT):
    """
    Return a second-pass prompt that enforces sentence length, word length,
    function-word density, and varied sentence starts on a draft rewrite.
    """
    if profile == PROFILE_ESSAY:
        return _build_essay_audit_prompt(tone, strength, mode, use_case, domain, style_note)

    tone_hint = TONE_HINTS.get(tone, TONE_HINTS[RewriteJob.TONE_PROFESSIONAL])
    use_case_hint = USE_CASE_HINTS.get(use_case, USE_CASE_HINTS[RewriteJob.USE_CASE_GENERAL])
    domain_banned = _domain_banned_line(domain)
    style_line = f"\nStyle note from the user: {style_note}\nApply it only if it does not conflict with the tightening rules." if style_note else ""

    return f"""You are a copy editor tightening a draft so it reads like a real person wrote it — not like Wikipedia, a textbook, or a detector-friendly essay bot.

You are given:
- ORIGINAL facts
- A DRAFT rewrite

Your job: tighten the draft only. Keep every fact, name, number, date, and technical term from the original. Do not add new facts. Never make the tone more formal than the draft.

### Tightening targets
- Keep the draft readable, but it should sound like a quick text, not a polished essay. A little roughness is fine.
- Average sentence length: 10-16 words.
- Split any sentence over 22 words.
- Include several short sentences (under 7 words). A few in a row is OK if it sounds like someone texting quickly.
- About half the sentences should be under 12 words.
- Use the shortest word that means the same thing. Replace long words with short ones.
- Function words should be about 40-45% of all words. Main function words: {", ".join(FUNCTION_WORDS)}.
- Repeat a key word or phrase 3-4 times naturally when it improves voice.
- Use contractions heavily.
- Vary sentence starters. Start many sentences with "And", "But", "So", "Plus", "Anyway", "Honestly", "Here's the thing", or "Just".
- Use "you" or "we" now and then.
- It is OK to keep a short fragment like "Obviously." or "Makes sense." if it feels natural.

### What to remove
- Three-item lists: "A, B, and C" → split into two sentences or use "and" pairs.
- Long comma chains and semicolons.
- Encyclopedic definitions: "X is a Y that..." → rewrite as "X is a Y. It...".
- Formal hedges: crucially, fundamentally, ultimately, notably, significantly, interestingly, additionally, furthermore, moreover, consequently, therefore, overall, in summary, in conclusion, needless to say, in today's world, it is important to note, it should be noted.
- Hype adjectives: dynamic, smart, legendary, crucial, fundamental, ultimate, significant, notable, robust, versatile, powerful, essential, vital, integral, pivotal, paramount, widespread, renowned, famous, recognized, acknowledged.
- Feature verbs: helps, allows, enables, assists, streamlines, optimizes, enhances, improves, facilitates, plays a role, serves as, acts as, functions as, can be used to, has the ability to, offers a way to, provides a way to, makes it easy to, makes it simple to, is designed to, is used for, is known for, is regarded as, is considered to be, is characterized by.
- Templated openers: It is, There is, There are, This is, That is, These are, Those are, One of the, Some of the, Many of the, Most of the, All of the, For example, In fact, Of course, Not only.
- Phrases: essential tool for, works well with, make data easy to, is a go-to tool for, with a mix of, connect the dots, I have developed skills in.{domain_banned}
{style_line}

### Vary sentence starters
Use a mix of: It's, There's, That, This, You can, And, But, So, Plus, Also, Honestly, Anyway, I'd say, To me, Here's the thing, Just.

### Strip encyclopedic residue
If any sentence still reads like a wiki line ("X is a Y played on…", "The objective is to…", "It is widely…", "also known as", "throughout history", "attracts millions"), rewrite that sentence into plain action or observation. Vary how each paragraph begins.

Tone: {tone_hint}
Format: {use_case_hint}

Return only the tightened text. No preamble, no explanation."""


def _client():
    """Build an OpenAI client or raise if the API key is missing."""
    key = settings.OPENAI_API_KEY
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=key, timeout=settings.OPENAI_TIMEOUT_SECONDS)


def _first_pass(
    text, tone, strength, mode, use_case, domain, style_note, profile=PROFILE_SHORT, regenerate=False
):
    """Generate a draft rewrite with the human-style system prompt."""
    client = _client()
    temperature = STRENGTH_TEMPERATURE.get(strength, 0.70)
    if profile == PROFILE_ESSAY:
        temperature = min(0.92, temperature + 0.12)
    user_message = text
    if profile == PROFILE_ESSAY:
        user_message = (
            "Rewrite every sentence. Keep the same number of paragraphs (blank line between them).\n\n"
            + text
        )
    if regenerate:
        user_message = "Produce a different phrasing from before.\n\n" + user_message

    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=temperature,
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(
                    tone, strength, mode, use_case, domain, style_note, profile=profile
                ),
            },
            {"role": "user", "content": user_message},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def _audit_pass(
    original, draft, tone, strength, mode, use_case, domain, style_note, profile=PROFILE_SHORT
):
    """Tighten the draft so it hits the human-style targets."""
    client = _client()
    audit_temp = 0.45 if profile == PROFILE_ESSAY else 0.52
    response = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=audit_temp,
        messages=[
            {
                "role": "system",
                "content": build_audit_prompt(
                    tone, strength, mode, use_case, domain, style_note, profile=profile
                ),
            },
            {
                "role": "user",
                "content": f"ORIGINAL:\n{original}\n\nDRAFT:\n{draft}",
            },
        ],
    )
    return (response.choices[0].message.content or "").strip()


def rewrite_chunk(
    text, tone, strength, mode, use_case, domain, style_note, profile=PROFILE_SHORT, regenerate=False
):
    """
    Rewrite one chunk using a multi-candidate + two-pass flow.

    1. Generate HUMANIZE_CANDIDATES first-pass drafts.
    2. Score them locally and pick the best one.
    3. Run the audit pass on the best draft to enforce style targets.

    This increases API cost (HUMANIZE_CANDIDATES + 1 calls per chunk) but
    makes the first click match the quality of the old "Try again" click.
    """
    candidates = [
        _first_pass(
            text,
            tone,
            strength,
            mode,
            use_case,
            domain,
            style_note,
            profile=profile,
            regenerate=regenerate,
        )
        for _ in range(settings.HUMANIZE_CANDIDATES)
    ]
    best_draft = pick_best_candidate(candidates, text, profile=profile)
    return _audit_pass(
        text, best_draft, tone, strength, mode, use_case, domain, style_note, profile=profile
    )


def humanize_text(text, tone, strength, mode, use_case, domain, style_note, regenerate=False):
    """
    Rewrite `text`, chunking if needed, and return (result, model_name).

    Chunks are joined with a blank line so paragraph breaks survive.
    """
    profile = detect_writing_profile(text)
    chunk_limit = (
        settings.HUMANIZE_ESSAY_CHUNK_WORDS
        if profile == PROFILE_ESSAY
        else settings.HUMANIZE_CHUNK_WORDS
    )
    pieces = chunk_text(text, chunk_limit)
    rewritten = [
        rewrite_chunk(
            piece,
            tone,
            strength,
            mode,
            use_case,
            domain,
            style_note,
            profile=profile,
            regenerate=regenerate,
        )
        for piece in pieces
    ]
    return "\n\n".join(rewritten), settings.OPENAI_MODEL


def run_humanize_job(
    user,
    original_text,
    tone,
    strength,
    mode,
    use_case,
    style_note="",
    regenerate=False,
):
    """
    Call OpenAI and store a RewriteJob.

    Domain is auto-detected from the original text before the prompt is built.
    Quota must already have been checked. Word count is saved only when
    status is OK so failed calls do not eat the weekly budget.
    Returns the saved RewriteJob (ok or failed).
    """
    words = count_words(original_text)
    domain = detect_domain(original_text)
    job = RewriteJob(
        user=user,
        original_text=original_text,
        tone=tone,
        strength=strength,
        mode=mode,
        use_case=use_case,
        domain=domain,
        style_note=style_note,
        word_count=0,
        model_name=settings.OPENAI_MODEL,
        status=RewriteJob.STATUS_FAILED,
    )
    try:
        result, model_name = humanize_text(
            original_text, tone, strength, mode, use_case, domain, style_note, regenerate=regenerate
        )
        job.humanized_text = result
        job.model_name = model_name
        job.word_count = words
        job.status = RewriteJob.STATUS_OK
    except RuntimeError as exc:
        job.error_message = str(exc)[:255]
    except OpenAIError:
        job.error_message = "The rewrite service is busy. Please try again in a moment."
    job.save()
    return job
