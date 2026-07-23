// Синтетический пример структуры данных прототипа.
// Реальный срез (prototype/data.js) в git не хранится — см. README.
// Чтобы прототип открылся из свежего клона: cp data.example.js data.js
const DATA = [
{
  "id": 1001,
  "platform": "tg",
  "username": "example_channel",
  "display_name": "Пример канала",
  "description": "Демонстрационный канал для прототипа витрины.\n\nПо вопросам сотрудничества: @example",
  "url": "https://t.me/example_channel",
  "avatar_url": null,
  "blogger_id": 501,
  "blogger_name": "Пример Автора",
  "subscribers": 128400,
  "views_avg": 41200,
  "er_percent": 3.4,
  "scraped_at": "2026-07-21T04:30:00+03:00",
  "categories": ["Новости и СМИ", "Историческое и познавательное"],
  "posts_30d": 84,
  "ads_90d": 11,
  "posts_90d": 240,
  "last_post_at": "2026-07-21T09:15:00+03:00",
  "views_organic": 43100,
  "views_ad": 35800,
  "views_spread": 62,
  "posts": [
    {"id": 1, "text": "Обычный пост канала: короткий текст, ссылка на источник.", "url": "https://t.me/example_channel/1",
     "views": 44200, "likes": 310, "reactions": 512, "comments": 44, "is_ad": false, "posted_at": "2026-07-20T12:00:00+03:00", "rn": 1},
    {"id": 2, "text": "Рекламный пост с маркировкой. Реклама. ООО «Пример», erid: 0000AbCdEf", "url": "https://t.me/example_channel/2",
     "views": 35100, "likes": 120, "reactions": 180, "comments": 9, "is_ad": true, "posted_at": "2026-07-18T15:30:00+03:00", "rn": 2},
    {"id": 3, "text": "Ещё один обычный пост, чтобы в карусели было что листать.", "url": "https://t.me/example_channel/3",
     "views": 46800, "likes": 402, "reactions": 630, "comments": 71, "is_ad": false, "posted_at": "2026-07-16T10:05:00+03:00", "rn": 3}
  ],
  "advertisers": [
    {"id": 1001, "aid": 1, "name_short": "ООО «Пример»", "name_full": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ \"ПРИМЕР\"",
     "entity_type": "ul", "cnt": 3, "last_at": "2026-07-18T15:30:00+03:00", "rn": 1, "total": 4, "repeat_n": 1},
    {"id": 1001, "aid": 2, "name_short": "ИП Пример", "name_full": "ИП ПРИМЕР",
     "entity_type": "fl", "cnt": 1, "last_at": "2026-06-02T11:00:00+03:00", "rn": 2, "total": 4, "repeat_n": 1}
  ],
  "adv_total": 4,
  "adv_repeat": 1,
  "history": [
    ["2026-04-26", 119800], ["2026-05-10", 122400], ["2026-05-24", 124100],
    ["2026-06-07", 125900], ["2026-06-21", 126800], ["2026-07-05", 127600], ["2026-07-19", 128400]
  ],
  "siblings": [
    {"id": 1002, "platform": "vk", "username": "example_group", "subs": 54300}
  ]
},
{
  "id": 1002,
  "platform": "vk",
  "username": "example_group",
  "display_name": "Пример канала",
  "description": "Та же площадка автора во ВКонтакте — нужна, чтобы проверить вывод площадок автора.",
  "url": "https://vk.com/example_group",
  "avatar_url": null,
  "blogger_id": 501,
  "blogger_name": "Пример Автора",
  "subscribers": 54300,
  "views_avg": 9800,
  "er_percent": 1.9,
  "scraped_at": "2026-07-21T04:31:00+03:00",
  "categories": ["Новости и СМИ"],
  "posts_30d": 41,
  "ads_90d": 4,
  "posts_90d": 118,
  "last_post_at": "2026-07-20T18:40:00+03:00",
  "views_organic": 10100,
  "views_ad": 8900,
  "views_spread": 88,
  "posts": [
    {"id": 11, "text": "Пост во ВКонтакте.", "url": "https://vk.com/example_group?w=wall-1_11",
     "views": 10400, "likes": 88, "reactions": 120, "comments": 12, "is_ad": false, "posted_at": "2026-07-20T18:40:00+03:00", "rn": 1}
  ],
  "advertisers": null,
  "adv_total": null,
  "adv_repeat": null,
  "history": [["2026-04-26", 52100], ["2026-05-24", 53200], ["2026-06-21", 53900], ["2026-07-19", 54300]],
  "siblings": [
    {"id": 1001, "platform": "tg", "username": "example_channel", "subs": 128400}
  ]
}
];
