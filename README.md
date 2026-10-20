# 💼 Shine Scraper

Shine Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Shine.com job data for free.

## ✨ What Can I Get?

- 💼 **220,000+ live jobs across India** — full description, skills, experience, applicant count & the employer's company profile
- 🔍 **Search with every Shine filter** — city, experience & salary bands, employment type, walk-ins, department, industry & date posted
- 🏢 **Every open job at any company** — Google, Microsoft, Accenture or Infosys, with company size, HQ, founded year & social links
- 📍 **7,700+ locations + autocomplete** — city IDs, WFH & hybrid, keyword suggestions with inferred skills & trending searches

## 🎥 Example: A Full Shine Job Ad

```json
{
  "id": "19680754",
  "title": "Web Solutions Engineer - Backend & AI Integration",
  "link": "https://www.shine.com/jobs/web-solutions-engineer-backend-ai-integration/google-india-pvt-ltd/19680754",
  "company": {
    "name": "Google India Pvt Ltd",
    "logo": "https://candidate-static.s3.ap-south-1.amazonaws.com/c/s1/images/candidate/company-logo/google_india_private_limited.png",
    "website": "https://about.google",
    "size": "10,001+ employees",
    "headquarters": "Hyderabad, India",
    "founded_year": 2004,
    "social_links": {
      "linkedin": "https://www.linkedin.com/company/google",
      "glassdoor": "https://www.glassdoor.com/Overview/Working-at-google"
    },
    "is_top_company": true
  },
  "locations": ["Bangalore"],
  "location_details": [{ "city": "Bangalore", "state": "Karnataka" }],
  "experience": { "label": "4 to 8 Yrs", "min_years": 4, "max_years": 8 },
  "industry": "IT Services & Consulting",
  "functional_areas": [{ "id": "1301", "name": "General / Other Software" }],
  "skills": ["system design", "fullstack development", "distributed data processing", "event streaming"],
  "employment_type": "regular",
  "shift_type": "full_time",
  "applicant_count": 4,
  "description_text": "Web Solutions Engineer, Technology and Insights Partnership Systems, Youtube India Minimum qualifications: Bachelor's degree in Computer Science, Electrical Engineering, Math or a related quantitative field ...",
  "posted_at": "2026-10-02T01:38:53Z",
  "expires_at": "2026-12-01T01:38:51Z"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Shine Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/shine-scraper
cd shine-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=19680754"
```

```json
{
  "id": "19680754",
  "title": "Web Solutions Engineer - Backend & AI Integration",
  "company": {
    "name": "Google India Pvt Ltd",
    "website": "https://about.google",
    "size": "10,001+ employees",
    "headquarters": "Hyderabad, India",
    "founded_year": 2004,
    "is_top_company": true
  },
  "locations": ["Bangalore"],
  "experience": { "label": "4 to 8 Yrs", "min_years": 4, "max_years": 8 },
  "industry": "IT Services & Consulting",
  "skills": ["system design", "version control", "fullstack development", "backend software development"],
  "applicant_count": 4,
  "posted_at": "2026-10-02T01:38:53Z",
  "expires_at": "2026-12-01T01:38:51Z"
}
```

All 9 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

9 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | The full job ad: description, skills, experience, applicants, employer profile |
| Search Jobs | `/jobs/search` | Up to 50 jobs per page with every filter and facets |
| Company Jobs | `/companies/jobs` | Every open job at a company, by name or URL |
| Similar Jobs | `/jobs/similar` | The jobs Shine recommends next to any job |
| Batch Job Details | `/jobs/batch` | Full details for up to 10 jobs in one call |
| Autocomplete | `/suggest` | Keyword suggestions with inferred skills, or city IDs |
| Locations | `/locations` | 7,700+ cities with state and ID, plus WFH and Hybrid |
| Filters | `/filters` | Every filter value, with live department and industry IDs |
| Trending Searches | `/trending` | Trending and most-clicked job searches with their links |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-shine-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-shine-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-shine-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "software engineer", "location": "Bangalore"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Shine Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Shine%20Scraper%20API.)

[![Ask Us by Email about Shine Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Shine%20Scraper%20API&body=I%20need%20help%20using%20the%20Shine%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**Jobstreet Scraper**](https://github.com/omkarcloud/jobstreet-scraper) — JobStreet & JobsDB jobs across 6 Asian markets: salaries, companies & reviews
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/shine-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/shine-scraper)
