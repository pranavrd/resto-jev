# Aspect labelling guidelines (batch 1)

You will label about 180 restaurant reviews at `#/label`. For each review you answer four questions, one per aspect: is it
mentioned, and if so how does the reviewer feel about it. These labels are the yardstick for Jev's aspect scoring (decision 0021),
so the aim is to record **what the text says**, not what you think of the place.

You see only the review text. You are not shown the star rating, the restaurant or any model answer, on purpose. Please do not look
them up. If you happen to know the place, label the text anyway.

## The four aspects

| Aspect | What counts |
|---|---|
| **food** | the food and drinks themselves: taste, quality, freshness, portion size, the menu |
| **atmosphere** | the place and its mood: decor, noise, music, cleanliness of the room, seating, crowding, the setting |
| **service** | the staff and how the visit was run: friendliness, attentiveness, speed, mistakes, waiting for a table or the check |
| **value** | what the reviewer paid compared with what they got: cheap, fair or overpriced for the quality and the portions |

## Not mentioned, or a level

Press **n** if the review says nothing about the aspect. Otherwise choose a level, 1 to 5:

| Key | Level | Means |
|---|---|---|
| 1 | Very negative | clearly negative: disappointed, angry, or calls it bad |
| 2 | Negative | more complaint than praise, or only so-so |
| 3 | Mixed or flat | praise and criticism both, or described without a judgement ("it was fine") |
| 4 | Positive | mostly good, a minor complaint or no enthusiasm |
| 5 | Very positive | clearly enthusiastic |

Hover a level on the page for the longer description Jev is given for that aspect. They are the same words.

## Rules that keep the labels honest

1. **Judge each aspect on its own.** A glowing review can grumble about price: value is negative, food is very positive. A furious
   review can still praise the room. Do not let the overall mood of the review decide an aspect. This is the point of the whole exercise.
2. **"Mentioned" needs something specific.** Dishes and drinks are food. Servers, waiting, the host, the bill are service. Decor, noise,
   music, seating, the view are atmosphere. Price, portions-for-the-price, "worth it" are value. General praise ("loved this place",
   "highly recommend") is not a mention of any aspect.
3. **A clause is enough.** "Great pasta, shame about the wait" mentions food (positive) and service (negative).
4. **Silence is not neutral.** If the review does not discuss an aspect, it is *not mentioned*, not level 3. Level 3 is for a review that
   does discuss it and lands in the middle.
5. **Take the text at its word.** Sarcasm counts as the opposite of what it literally says. Comparisons to another restaurant describe
   what the reviewer thinks of *this* one: "not as good as the place down the road" is a negative on whatever is compared.
6. **Portions** on their own are food. "Huge portions for the price" is also value, positive.
7. **Takeaway and delivery:** the food is food. The courier or the order handling is service. Packaging is not any aspect.
8. **A review about something else** (a hotel, a different restaurant, spam) still gets labelled by what it says about these four
   aspects, usually all *not mentioned*.
9. **Cannot tell** is not an option here on purpose: if the text is too thin to judge an aspect, it is not mentioned.

## Invented examples

| Text | Food | Atmosphere | Service | Value |
|---|---|---|---|---|
| "The pasta was cold and the sauce tasted like ketchup." | 1 | n | n | n |
| "Lovely room, but so loud we had to shout. Food was fine." | 3 | 2 | n | n |
| "Staff couldn't have been nicer. Pricey for what you get though." | n | n | 5 | 2 |
| "Best tacos in town, and cheap!" | 5 | n | n | 5 |
| "Waited 45 minutes, waiter forgot our drinks. Never again." | n | n | 1 | n |
| "Loved everything about this place!" | n | n | n | n |

## Working habits

- About 30 to 60 seconds a review is right. Go with your first reading; do not deliberate.
- Some reviews appear twice, spaced well apart. This is deliberate, to measure how consistent a labeller is. Do not try to remember
  your first answer; label what you see.
- Work in sessions of 30 to 40 reviews. The page records the time per review, and a tired labeller is a noisy one.
- Use **u** to undo the last saved review if you hit a wrong key. Backspace steps back within the review.

## How the labels will be used

Batch 1 judges Jev's scores and nothing else: the agreement, the halo question and the value question (decision 0021). It is **never**
used to tune the composite weights or the rating model. Anything tuned later uses later batches, so the labels that choose a setting are
not the ones that judge it.
