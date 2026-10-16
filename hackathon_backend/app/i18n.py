"""Citizen and team notifications in English, Hindi and Marathi.

Machine translations written for the demo; have a native speaker review them
before a real rollout.
"""

TEMPLATES = {
    "ALLOCATED": {
        "en": "Your group {group} is allocated to {site} at {time}.",
        "hi": "आपके समूह {group} को {time} बजे {site} आवंटित किया गया है।",
        "mr": "तुमच्या गट {group} ला {time} वाजता {site} येथे जागा देण्यात आली आहे.",
    },
    "DIVERTED": {
        "en": "{site_from} is crowded. Please go to {site} at {time} instead.",
        "hi": "{site_from} में भीड़ है। कृपया {time} बजे {site} जाएँ।",
        "mr": "{site_from} येथे गर्दी आहे. कृपया {time} वाजता {site} येथे जा.",
    },
    "REJECTED": {
        "en": "Sorry, no safe slot is available for group {group} right now. Please try a later time.",
        "hi": "क्षमा करें, समूह {group} के लिए अभी कोई सुरक्षित स्लॉट उपलब्ध नहीं है। कृपया बाद में प्रयास करें।",
        "mr": "क्षमस्व, गट {group} साठी सध्या सुरक्षित वेळ उपलब्ध नाही. कृपया नंतर प्रयत्न करा.",
    },
    "REROUTED": {
        "en": "Update: {site_from} is now overcrowded. Your group {group} has been moved to {site} at {time}.",
        "hi": "सूचना: {site_from} में अब बहुत भीड़ है। आपके समूह {group} को {time} बजे {site} भेजा गया है।",
        "mr": "सूचना: {site_from} येथे आता खूप गर्दी आहे. तुमच्या गट {group} ला {time} वाजता {site} येथे हलवण्यात आले आहे.",
    },
    "SWM_TASK": {
        "en": "Waste pickup needed at {site}: bins expected to reach {fill}% soon.",
        "hi": "{site} पर कचरा उठाने की ज़रूरत है: डिब्बे जल्द ही {fill}% तक भर सकते हैं।",
        "mr": "{site} येथे कचरा उचलणे आवश्यक आहे: डबे लवकरच {fill}% भरतील.",
    },
}


def notify(kind: str, **values) -> dict[str, str]:
    return {lang: template.format(**values) for lang, template in TEMPLATES[kind].items()}
