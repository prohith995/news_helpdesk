"""Mock news data for testing and development without API keys."""

from datetime import datetime, timedelta
from ..schemas import Article, SourceInfo


def get_mock_articles_framing(topic: str) -> list[Article]:
    """Generate mock articles for framing divergence testing.

    Returns articles from different sources with varying perspectives.
    """
    base_time = datetime.now()

    return [
        Article(
            title=f"Tech Giants Push Back Against New {topic} Rules",
            url="https://example.com/techcrunch/1",
            source=SourceInfo(name="TechCrunch", url="https://techcrunch.com", bias_label="center-left"),
            published_at=base_time - timedelta(hours=2),
            snippet="Major technology companies are expressing concerns about proposed regulations, arguing they could stifle innovation and put American companies at a disadvantage globally.",
            content="Major technology companies are expressing concerns about proposed regulations, arguing they could stifle innovation and put American companies at a disadvantage globally. Industry leaders warn that overly restrictive rules could push development offshore.",
        ),
        Article(
            title=f"Consumer Groups Welcome Stricter {topic} Oversight",
            url="https://example.com/consumerreports/1",
            source=SourceInfo(name="Consumer Reports", url="https://consumerreports.org", bias_label="center"),
            published_at=base_time - timedelta(hours=5),
            snippet="Consumer advocacy organizations are applauding new regulatory proposals, saying they will protect citizens from potential harms while still allowing for technological progress.",
            content="Consumer advocacy organizations are applauding new regulatory proposals, saying they will protect citizens from potential harms while still allowing for technological progress. Groups emphasize the need for transparency and accountability.",
        ),
        Article(
            title=f"European Regulators Set Aggressive Timeline for {topic} Rules",
            url="https://example.com/reuters/1",
            source=SourceInfo(name="Reuters", url="https://reuters.com", bias_label="center"),
            published_at=base_time - timedelta(hours=8),
            snippet="EU officials have outlined an ambitious timeline for implementing comprehensive regulations, potentially setting a global standard for other nations to follow.",
            content="EU officials have outlined an ambitious timeline for implementing comprehensive regulations, potentially setting a global standard for other nations to follow. The Brussels effect may once again shape international policy.",
        ),
        Article(
            title=f"Free Market Advocates Warn Against Heavy-Handed {topic} Regulation",
            url="https://example.com/wsj/1",
            source=SourceInfo(name="Wall Street Journal", url="https://wsj.com", bias_label="center-right"),
            published_at=base_time - timedelta(hours=12),
            snippet="Economic analysts argue that government intervention could harm competitiveness and drive investment to less regulated markets, ultimately hurting consumers.",
            content="Economic analysts argue that government intervention could harm competitiveness and drive investment to less regulated markets, ultimately hurting consumers. They advocate for industry self-regulation as an alternative.",
        ),
        Article(
            title=f"Safety Experts Call for Immediate Action on {topic}",
            url="https://example.com/wired/1",
            source=SourceInfo(name="Wired", url="https://wired.com", bias_label="center-left"),
            published_at=base_time - timedelta(hours=18),
            snippet="Researchers and safety advocates are urging lawmakers not to delay, citing potential risks that could affect millions of users if left unaddressed.",
            content="Researchers and safety advocates are urging lawmakers not to delay, citing potential risks that could affect millions of users if left unaddressed. They point to recent incidents as evidence that action is needed now.",
        ),
    ]


def get_mock_articles_claim(claim: str) -> list[Article]:
    """Generate mock articles for claim checking testing.

    Returns articles that provide evidence for/against a claim.
    """
    base_time = datetime.now()

    return [
        Article(
            title="Company Confirms Major Restructuring, Thousands Affected",
            url="https://example.com/bloomberg/1",
            source=SourceInfo(name="Bloomberg", url="https://bloomberg.com", bias_label="center"),
            published_at=base_time - timedelta(days=1),
            snippet="In a press release Tuesday, the company confirmed significant workforce reductions as part of a broader restructuring effort aimed at improving operational efficiency.",
            content="In a press release Tuesday, the company confirmed significant workforce reductions as part of a broader restructuring effort aimed at improving operational efficiency. The company stated that approximately 10,000 positions would be eliminated over the next quarter.",
        ),
        Article(
            title="Industry Analyst Breaks Down the Layoff Numbers",
            url="https://example.com/cnbc/1",
            source=SourceInfo(name="CNBC", url="https://cnbc.com", bias_label="center"),
            published_at=base_time - timedelta(days=1, hours=6),
            snippet="Financial analysts are weighing in on the announced job cuts, with some noting the numbers may be higher than initially reported when contractor positions are included.",
            content="Financial analysts are weighing in on the announced job cuts, with some noting the numbers may be higher than initially reported when contractor positions are included. Official filings suggest the total could reach 12,000.",
        ),
        Article(
            title="Union Representatives Question Official Layoff Figures",
            url="https://example.com/guardian/1",
            source=SourceInfo(name="The Guardian", url="https://theguardian.com", bias_label="center-left"),
            published_at=base_time - timedelta(hours=18),
            snippet="Worker representatives are disputing company claims about the scope of layoffs, saying internal communications suggest a much larger number of positions are at risk.",
            content="Worker representatives are disputing company claims about the scope of layoffs, saying internal communications suggest a much larger number of positions are at risk. They estimate the real figure could be closer to 15,000.",
        ),
        Article(
            title="Company Stock Rises Despite Layoff Announcement",
            url="https://example.com/ft/1",
            source=SourceInfo(name="Financial Times", url="https://ft.com", bias_label="center-right"),
            published_at=base_time - timedelta(hours=12),
            snippet="Markets responded positively to news of the workforce reduction, with shares climbing 4% in after-hours trading as investors welcomed cost-cutting measures.",
            content="Markets responded positively to news of the workforce reduction, with shares climbing 4% in after-hours trading as investors welcomed cost-cutting measures. The company confirmed approximately 10,000 layoffs in its earnings call.",
        ),
    ]


def get_mock_articles_insufficient() -> list[Article]:
    """Generate insufficient articles to trigger abstention."""
    return [
        Article(
            title="Brief Update on Topic",
            url="https://example.com/single/1",
            source=SourceInfo(name="Single Source", url="https://example.com"),
            published_at=datetime.now(),
            snippet="A brief update.",
        ),
    ]
