import re
import uuid
from ..base import BaseCollector
from ...services import serp_service, hunter_service
from ...database.repository import get_collector_evidence, save_contacts
from ...utils.http_client import get as http_get
from ...utils.logger import get_logger

logger = get_logger(__name__)


class ContactCollector(BaseCollector):
    name = "contact"

    async def collect(self) -> dict:
        company = self.app.get("developer") or self.app.get("app_name", "")
        website = self.app.get("developer_website") or ""
        domain  = self._extract_domain(website)
        app_id  = self.app.get("id")

        contacts = []

        # 1. Reuse founder name from EC4 social if already collected
        if app_id:
            social_ev = await get_collector_evidence(self.db, uuid.UUID(str(app_id)), "social")
            if social_ev and social_ev.data:
                founder    = social_ev.data.get("founder_name")
                founder_li = social_ev.data.get("founder_linkedin_url")
                if founder:
                    contacts.append({
                        "name": founder, "title": "Founder/CEO",
                        "email": None, "linkedin_url": founder_li,
                        "twitter_url": None, "confidence": 0.7,
                        "source": "social_collector", "is_primary": True,
                    })

        # 2. Web search for LinkedIn profiles (SerpAPI or DDG fallback)
        serp = await serp_service.search(
            f'"{company}" founder OR CEO OR "co-founder" site:linkedin.com/in', num=3
        )
        for r in serp:
            name = r.get("title", "").split(" - ")[0].strip()
            if name and not any(c["name"] == name for c in contacts):
                contacts.append({
                    "name": name, "title": self._extract_title(r.get("title", "")),
                    "email": None, "linkedin_url": r.get("link"),
                    "twitter_url": None, "confidence": 0.5,
                    "source": "serp_linkedin", "is_primary": len(contacts) == 0,
                })

        # 3. Hunter.io for email (if key available)
        if domain:
            try:
                hunter_emails = await hunter_service.domain_search(domain)
                for e in hunter_emails[:3]:
                    name = f"{e.get('first_name', '')} {e.get('last_name', '')}".strip()
                    existing = next((c for c in contacts if c["name"] == name), None)
                    if existing:
                        existing["email"] = e.get("value")
                        existing["confidence"] = min(1.0, existing["confidence"] + 0.2)
                    elif name:
                        contacts.append({
                            "name": name,
                            "title": e.get("position", ""),
                            "email": e.get("value"),
                            "linkedin_url": None, "twitter_url": None,
                            "confidence": e.get("confidence", 0) / 100,
                            "source": "hunter_io",
                            "is_primary": len(contacts) == 0,
                        })
            except Exception as e:
                logger.warning("contact.hunter.failed", error=str(e)[:80])

        # 4. FREE FALLBACK: scrape company website for team/about page
        if not contacts and website:
            scraped = await self._scrape_team_page(website, company)
            contacts.extend(scraped)

        # Write to contacts table
        if contacts and app_id:
            await save_contacts(self.db, uuid.UUID(str(app_id)), contacts)

        primary = next((c for c in contacts if c.get("is_primary")), contacts[0] if contacts else None)
        signals = []
        if primary and primary.get("email"):
            signals.append(f"Found contact: {primary['name']} ({primary['email']})")
        elif primary:
            signals.append(f"Found contact: {primary['name']} via {primary['source']}")
        else:
            signals.append("No direct contact found — manual lookup needed")

        return {
            "data": {
                "contacts":        contacts,
                "primary_contact": primary,
            },
            "confidence": 0.8 if (primary and primary.get("email")) else (0.4 if primary else 0.1),
            "signals": signals,
            "error": None,
        }

    async def _scrape_team_page(self, website: str, company: str) -> list[dict]:
        """
        Free fallback: try /about, /team, /founders pages on the company website.
        Extract names and emails via regex — no API key needed.
        """
        contacts = []
        base = website.rstrip("/")
        paths = ["/about", "/team", "/about-us", "/founders", "/leadership", "/contact"]

        for path in paths:
            try:
                resp = await http_get(f"{base}{path}")
                html = resp.text

                # Extract emails
                emails = list(set(re.findall(
                    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html
                )))
                emails = [e for e in emails if not any(skip in e.lower() for skip in [
                    "example", "test", "noreply", "no-reply", "support", "info@", "hello@",
                    "enteryour", "youremail", "your@", "email@", "yourname", "user@",
                    "admin@", "webmaster", "placeholder", "sample",
                ])]

                # Extract LinkedIn profiles
                li_urls = list(set(re.findall(r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-]+', html)))

                # Try to find "Founder" or "CEO" near a name pattern
                founder_patterns = [
                    r'([A-Z][a-z]+ [A-Z][a-z]+)[^<]*(?:Founder|CEO|Co-founder|Director)',
                    r'(?:Founder|CEO|Co-founder|Director)[^<]*?([A-Z][a-z]+ [A-Z][a-z]+)',
                ]
                names = []
                for pat in founder_patterns:
                    names.extend(re.findall(pat, html))

                if names or emails or li_urls:
                    name = names[0] if names else company
                    email = emails[0] if emails else None
                    li_url = li_urls[0] if li_urls else None
                    contacts.append({
                        "name": name, "title": "Founder/CEO",
                        "email": email, "linkedin_url": li_url,
                        "twitter_url": None, "confidence": 0.4,
                        "source": "website_scrape", "is_primary": True,
                    })
                    logger.info("contact.website_scrape.found",
                                path=path, name=name, has_email=bool(email))
                    break
            except Exception:
                continue

        return contacts

    def _extract_domain(self, url: str) -> str:
        if not url:
            return ""
        url = url.replace("https://", "").replace("http://", "").split("/")[0]
        return url.lstrip("www.")

    def _extract_title(self, linkedin_title: str) -> str:
        parts = linkedin_title.split(" - ")
        return parts[1].strip() if len(parts) > 1 else "Unknown"
