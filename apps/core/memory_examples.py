"""Clearly disclosed fictional memories for previewing the separate travel journal."""
from datetime import date


DEMO_MEMORIES = [
    ('morocco', 'Rabat', 'demo-memory-rabat-river', 'An afternoon above the river', date(2026, 4, 12), 'rabat',
     'The river caught the afternoon light as our imagined group paused above the Bouregreg. In this fictional memory, Samira, a made-up guide, invited everyone to notice one detail they wanted to remember.\n\nA doorway, a fishing boat, a patch of blue: the conversation became a collection of small discoveries. The group moved slowly, leaving room for questions, photographs and an unhurried pause.\n\nThis is a fictional sample story created to preview our travel journal. Samira, the travelers and the illustrated scene do not represent an actual Culture Hop Tours trip. The image is AI-generated and will be replaced with real trip photographs.'),
    ('morocco', 'Marrakech', 'demo-memory-marrakech-craft', 'The story behind a painted bowl', date(2026, 5, 9), 'marrakech',
     'A blue-and-white bowl became the conversation starter in this imagined Marrakech afternoon. Our fictional group gathered around a craft display, with Nabil, an invented guide, helping everyone look beyond the finished object.\n\nThe patterns suggested different stories to different travelers. There was time to look closely, exchange impressions and enjoy the courtyard before continuing through the city. In this sample memory, the highlight was the shared curiosity.\n\nThis is fictional demonstration content, not a report of a completed company tour or a customer testimonial. The guide and travelers are invented, and the image is AI-generated. Real photographs and memories will replace this example later.'),
    ('nigeria', 'Lagos', 'demo-memory-lagos-creative', 'A shared moment of colour in Lagos', date(2026, 7, 18), 'lagos',
     'Colour drew our imagined group into the conversation. In this fictional Lagos memory, Ada, an invented guide, introduced a small group to a creative studio filled with original textile-inspired patterns.\n\nA fabric unfolded across the table and everyone noticed something different: a shape, a rhythm, a combination of colours. The scene imagines travel as an exchange of perspectives, with time to listen and connect.\n\nThis sample memory and its AI-generated image are provided only to demonstrate the journal. Ada, the travelers, the studio and the visit are fictional. They are not evidence of a real Culture Hop Tours event or an actual guide relationship.'),
]


def seed_memory_examples(registry, alias='default'):
    Country=registry.get_model('core','Country')
    Post=registry.get_model('core','BlogPost')
    count=0
    for country, city, slug, title, trip_date, starter_image, content in DEMO_MEMORIES:
        Country.objects.using(alias).get_or_create(slug=country,defaults={'name':country.title(),'is_active':True})
        _, created=Post.objects.using(alias).get_or_create(slug=slug,defaults={
            'country':country,'region_id':country,'title':title,'city':city,'trip_date':trip_date,
            'is_demo':True,'story_kind':'memory','starter_image':starter_image,'content':content})
        count+=int(created)
    return count
