## Парсер товаров с приложения 4lapy.ru

Интересная задача, которую прислали в качестве тестового задания с пометкой _super hard_:

### 1. Что сказали сделать
Есть приложение в Google Store [Четыре Лапы - зоомагазин](https://play.google.com/store/apps/details?id=com.appteka.lapy)<br>
Необходимо написать парсер этой торговой площадки, любой её категории. Ходить на API, которое использует приложение.

### 2. Как делалось или что оказалось ~~сложным~~ интересным

Чтобы определить ручки, на которые ходит приложение, пришлось найти способ снифферить трафик с приложения.<br>
Спрашиваю Bing AI, что там сегодня в тренде по снифферингу трафика с мобилок и попадаю на [статью Харба](https://habr.com/ru/articles/719272/),
которая по полочкам раскладывает, на первый взгляд, тривиальный алгоритм действий с применением Burp Suite:
1. Подсунуть сертификат Burp'а в хранилище user-trusted сертификатов
2. Пересобрать apk приложения для патчинга на доверие хранилищам собственно-импортированных сертификатов 
3. Прокинуть проксю на адрес Burp
4. Слушать трафик, готово.

### Что пошло не по плану

Но для начала то, что пошло по плану :)

Что-то в моей голове подсказало, что в мобильном приложении [Adguard](https://adguard.com/en/adguard-android/overview.html) есть полезности,
связанные с фильтрацией трафика и его перенаправлении, и я не ошибся: Settings > Filtering > Network > Proxy приводят вас на страницу выбора приложений,
проксируемых через настраиваемый адрес сервера

<img src="https://i.imgur.com/S7eGeS1.jpeg" width="200"/>

Удобно направить только интересующий вас трафик к прокси-серверу, в отличие от способа настройки полного проксирования из статьи.

**Решающий момент**: запускаю приложение (которое, кстати, не требует обязательной авторизации), хитро слушаю трафик,
переношу запросы в Postman и обнаруживаю, что помимо заголовка с Bearer токеном в каждом запросе отправляется два обязательных параметра `token` и `sign`,
и последний всё время разный (разработчики подсуетились и впилили решение от простого парсинга):

> https://4lapy.ru/api/city_list_users/?token=686add0e524fa41a3bf7bcc81dcef15b&sign=f9997f6b01337c23ff805f07e1f96136

Тут-то стало понятно, почему задача помечена как _super hard_.

### И пошёл я...

И пошёл я искать инструменты ([dex2jar](https://github.com/pxb1988/dex2jar), [javadecompilers](http://www.javadecompilers.com/)
или от [IntelliJ](https://plugins.jetbrains.com/plugin/7100-java-decompiler)), чтобы декомпилировать байт-код приложения
в _.java_ файлы для дальнейшего изучения.

Каким-то поисковым чудом я разобрался в коде, переменные, методы и пакеты которого в большинстве своём были названы буквами английского алфавита,
и вышел на метод в пакете с ~~громко-кричащим~~ названием `w`, код которого, после собственноручного "рефакторинга" и "именования" выглядел так:
```java
public final Map<String, String> resolve_sequre_params(@NotNull Map<String, String> queries) {
      LinkedHashMap result_queries = new LinkedHashMap();
      result_queries.putAll(queries);

      ArrayList list = new ArrayList();
      Iterator queries_iter = result_queries.values().iterator();

      while(queries_iter.hasNext()) {
         list.add(this.hash_string_md5((String)queries_iter.next()));
      }

      CollectionsKt.sort(list);
      Iterator hashed_queries_iter = list.iterator();
      
      String sign;
      StringBuilder string_builder;
      for(sign = "ABCDEF00G"; hashed_queries_iter.hasNext(); sign = string_builder.toString()) {
         String hashed_query = (String)hashed_queries_iter.next();
         string_builder = new StringBuilder();
         string_builder.append(sign);
         string_builder.append(hashed_query);
      }

      result_queries.put("sign", this.hash_string_md5(sign));
      return result_queries;
   }
```

Дедлайн выполнения подходил к концу, мозговые ресурсы после изучения декомпелированной паутины истощились,
поэтому я закинул код в Bing AI и попросил перевести на Python:

```python
import hashlib
from collections import OrderedDict

def hash_string_md5(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()

def resolve_secure_params(queries):
    result_queries = OrderedDict(queries)
    
    # Сортируем значения запросов и хешируем их
    sorted_hashed_values = sorted(hash_string_md5(value) for value in result_queries.values())
    
    # Конкатенируем отсортированные хешированные значения с начальным знаком
    sign = "ABCDEF00G"
    for hashed_value in sorted_hashed_values:
        sign += hashed_value
    
    # Хешируем окончательный знак и добавляем его в результат запросов
    result_queries['sign'] = hash_string_md5(sign)
    
    return result_queries

# Пример использования:
queries = {
    "param1": "value1",
    "param2": "value2"
}

# Вызываем функцию и печатаем результат
secure_params = resolve_secure_params(queries)
print(secure_params)
```
> Этот метод принимает словарь параметров, сортирует их значения, хеширует каждое значение с помощью MD5,
затем конкатенирует их с начальной строкой и добавляет финальный хеш в качестве подписи (sign) в словарь. Если у вас есть дополнительные вопросы или нужна помощь, пожалуйста, сообщите мне.

Конец