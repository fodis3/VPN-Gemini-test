package engine

import (
	"encoding/json"
	"net/url"
	"regexp"
	"strings"
)

var countryField = regexp.MustCompile(`["']vXmutd["']\s*:\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')`)
var firstCountry = regexp.MustCompile(`^\s*\[?\s*["']([A-Z]{2})["']\s*(?:,|\]|$)`)
var countryOnly = regexp.MustCompile(`^[A-Z]{2}$`)
var titlePattern = regexp.MustCompile(`(?is)<title[^>]*>(.*?)</title>`)
var scriptPattern = regexp.MustCompile(`(?is)<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>`)
var whitespace = regexp.MustCompile(`\s+`)
var regionBanner = regexp.MustCompile(`(?:isn['’]t|not|is not)(?: currently)? (?:supported|available) in your country`)

func extractCountry(html string) string {
	at := strings.Index(html, "vXmutd")
	if at < 0 {
		return ""
	}
	lo := max(0, at-12)
	hi := min(len(html), at+4096)
	fragment := html[lo:hi]
	for range 3 {
		match := countryField.FindStringSubmatch(fragment)
		if len(match) > 1 {
			token := match[1]
			if strings.HasPrefix(token, "'") {
				token = `"` + strings.ReplaceAll(strings.Trim(token, "'"), `"`, `\"`) + `"`
			}
			var value string
			if json.Unmarshal([]byte(token), &value) != nil {
				return ""
			}
			country := value
			if !countryOnly.MatchString(value) {
				parts := firstCountry.FindStringSubmatch(strings.TrimPrefix(value, "%.@."))
				if len(parts) < 2 {
					return ""
				}
				country = parts[1]
			}
			if country == "XX" || country == "ZZ" {
				return ""
			}
			return country
		}
		fragment = strings.ReplaceAll(strings.ReplaceAll(fragment, `\"`, `"`), `\'`, `'`)
	}
	return ""
}
func classify(code int, finalURL, html string) Result {
	r := Result{Status: "UNKNOWN", Country: extractCountry(html), HTTPCode: code, FinalURL: finalURL}
	if t := titlePattern.FindStringSubmatch(html); len(t) > 1 {
		r.Title = whitespace.ReplaceAllString(t[1], " ")
		if len(r.Title) > 160 {
			r.Title = r.Title[:160]
		}
	}
	lower := strings.ToLower(scriptPattern.ReplaceAllString(html, " "))
	u, _ := url.Parse(finalURL)
	host := ""
	if u != nil {
		host = u.Hostname()
	}
	switch {
	case code == 429:
		r.Status = "RATE_LIMIT"
		r.Detail = "Google ограничил частоту запросов. Повторите позже."
	case strings.Contains(finalURL, "/sorry/") || strings.Contains(lower, "our systems have detected unusual traffic"):
		r.Status = "CAPTCHA"
		r.Detail = "Google запросил CAPTCHA."
	case host == "accounts.google.com":
		r.Status = "LOGIN"
		r.Detail = "Google перенаправил на вход в аккаунт."
	case code < 200 || code > 299:
		r.Status = "ERROR"
		r.Detail = "Ошибка HTTP. " + r.Title
	case strings.Contains(finalURL, "/unavailable") || regionBanner.MatchString(lower) || strings.Contains(lower, "недоступен в вашей стране") || strings.Contains(lower, "не поддерживается в вашей стране"):
		r.Status = "BLOCKED"
		r.Detail = "На странице явно указано региональное ограничение."
	case host != "gemini.google.com":
		r.Detail = "Вместо Gemini получен ответ другого сайта. Проверьте конечный URL."
	case strings.Contains("|AF|BY|CU|IR|KP|RU|SY|", "|"+r.Country+"|") && r.Country != "":
		r.Status = "BLOCKED"
		r.Detail = "Регион Google " + r.Country + " отсутствует в списке доступности веб-версии Gemini (20.10.2026)."
	case r.Country == "CN":
		r.Status = "LOGIN"
		r.Detail = "Регион CN: по справке Google доступ только для Workspace."
	case r.Country != "":
		r.Status = "OK"
		r.Detail = "Ответ Gemini получен; регион Google " + r.Country + ", признаков ограничения нет. Доступ аккаунта и генерация модели не проверялись."
	default:
		r.Detail = "Страница получена, но регион Google из vXmutd не определён. HTML и HTTP 200 сами по себе не подтверждают доступность."
	}
	return r
}
