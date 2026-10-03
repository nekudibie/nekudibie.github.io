"""Python basics: eight short lessons. References point at the official tutorial sections
(https://docs.python.org/3/tutorial/). Examples are verified by tests/unit/test_tutor.py."""

from ..course import Check, Course, Example, Exercise, Lesson

TUT = "https://docs.python.org/3/tutorial/"

COURSE = Course(
    id="python-basics",
    title="Python basics",
    description="From first expressions to reading a file safely: eight 30-minute lessons with exercises you check by reading and running your own code.",
    lessons=[
        Lesson(
            id="l1-numbers-strings",
            title="Numbers, strings and print",
            objectives=["Use Python as a calculator", "Tell integers, floats and strings apart", "Print values with print()"],
            explanation=(
                "Python evaluates expressions and prints results. Whole numbers are int, decimals are float, text in quotes is str. "
                "Division with / always gives a float; // gives the whole-number part; % gives the remainder. "
                "print() writes values to the screen separated by spaces; type() tells you what kind of value you have."
            ),
            examples=[
                Example(code="print(7 + 3 * 2)\nprint(17 / 5)\nprint(17 // 5, 17 % 5)", output="13\n3.4\n3 2", note="Multiplication binds tighter than addition."),
                Example(code="print(type(42), type(2.5), type('hi'))", output="<class 'int'> <class 'float'> <class 'str'>"),
                Example(code="name = 'Neku'\nprint('Hello, ' + name + '!')\nprint(f'{name} has {len(name)} letters')", output="Hello, Neku!\nNeku has 4 letters", note="f-strings put values inside text."),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Write a program that stores the number of minutes in a day in a variable and prints: 'A day has 1440 minutes' using an f-string.",
                    starter="minutes = 24 * 60\n# print the sentence with an f-string\n",
                    checks=[
                        Check(kind="requires_node", value="JoinedStr", message="Use an f-string (f'...') rather than joining with +."),
                        Check(kind="requires_call", value="print", message="The program must print the sentence."),
                        Check(kind="output_equals", value="A day has 1440 minutes", message="The printed text should read exactly: A day has 1440 minutes"),
                    ],
                    hints=["An f-string starts with f and uses {curly braces} for values.", "24 * 60 is 1440; keep the arithmetic in the variable, not in the text."],
                    topics=["print", "f-strings", "arithmetic"], expected_output="A day has 1440 minutes",
                ),
            ],
            topics=["print", "types", "arithmetic", "f-strings"],
            references=[TUT + "introduction.html#numbers", TUT + "introduction.html#text", TUT + "inputoutput.html#formatted-string-literals"],
            next_steps="Next: variables change over time, and strings have useful methods.",
        ),
        Lesson(
            id="l2-variables-strings",
            title="Variables and string methods",
            objectives=["Reassign and update variables", "Use .upper(), .lower(), .strip(), .replace()", "Index and slice strings"],
            explanation=(
                "A variable is a name for a value; assigning again replaces the value. Strings cannot be changed in place, "
                "so methods like .upper() return a new string. Indexing starts at 0 and negative indexes count from the end; "
                "a slice s[a:b] takes positions a up to but not including b."
            ),
            examples=[
                Example(code="count = 1\ncount = count + 1\ncount += 1\nprint(count)", output="3"),
                Example(code="s = '  Desk Lamp '\nprint(s.strip().lower())\nprint(s.strip().replace('Lamp', 'Light'))", output="desk lamp\nDesk Light"),
                Example(code="word = 'python'\nprint(word[0], word[-1], word[1:4])", output="p n yth"),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Given email = '  Neku.I@Example.com ', print it cleaned: no surrounding spaces and all lower case.",
                    starter="email = '  Neku.I@Example.com '\n",
                    checks=[
                        Check(kind="requires_call", value="strip", message="Remove the surrounding spaces with .strip()."),
                        Check(kind="requires_call", value="lower", message="Lower-case it with .lower()."),
                        Check(kind="output_equals", value="neku.i@example.com", message="Expected output: neku.i@example.com"),
                    ],
                    hints=["Methods can be chained: value.strip().lower()."],
                    topics=["strings", "methods"], expected_output="neku.i@example.com",
                ),
                Exercise(
                    id="e2", prompt="Print the first three letters and the last letter of the word 'companion' using slicing and a negative index.",
                    checks=[
                        Check(kind="requires_node", value="Slice", message="Use a slice like word[0:3]."),
                        Check(kind="contains_text", value="-1", message="Use a negative index for the last letter."),
                        Check(kind="output_equals", value="com n", message="Expected output: com n"),
                    ],
                    hints=["word[0:3] is the first three letters.", "word[-1] is the last letter."],
                    topics=["strings", "slicing"], expected_output="com n",
                ),
            ],
            topics=["variables", "strings", "slicing"],
            references=[TUT + "introduction.html#text"],
        ),
        Lesson(
            id="l3-lists",
            title="Lists",
            objectives=["Create lists and read items by index", "Append, insert and remove items", "Use len(), sum(), min(), max() and sorted()"],
            explanation=(
                "A list holds an ordered sequence of values and can change: .append(x) adds to the end, .insert(i, x) adds at a position, "
                ".pop() removes and returns the last item. Built-ins work on lists: len gives the count, sum adds numbers, sorted returns a new ordered list."
            ),
            examples=[
                Example(code="temps = [20.5, 19.0, 22.1]\ntemps.append(18.4)\nprint(len(temps), min(temps), max(temps))\nprint(sorted(temps))", output="4 18.4 22.1\n[18.4, 19.0, 20.5, 22.1]"),
                Example(code="shopping = ['tea', 'rice']\nshopping.insert(0, 'milk')\nlast = shopping.pop()\nprint(shopping, last)", output="['milk', 'tea'] rice"),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Start with scores = [71, 88, 64]. Append 90, then print the average rounded to one decimal place.",
                    starter="scores = [71, 88, 64]\n",
                    checks=[
                        Check(kind="requires_call", value="append", message="Add 90 with .append(90)."),
                        Check(kind="requires_call", value="sum", message="Use sum(scores) for the total."),
                        Check(kind="requires_call", value="round", message="Round the result with round(value, 1)."),
                        Check(kind="output_equals", value="78.2", message="Expected output: 78.2 (313 / 4 = 78.25, rounds to 78.2)"),
                    ],
                    hints=["Average is sum(scores) / len(scores).", "round(78.25, 1) is 78.2 because of banker's rounding; that is correct Python behaviour."],
                    topics=["lists", "builtins"], expected_output="78.2",
                ),
            ],
            topics=["lists", "builtins"],
            references=[TUT + "introduction.html#lists", TUT + "datastructures.html#more-on-lists"],
        ),
        Lesson(
            id="l4-loops",
            title="for loops and range()",
            objectives=["Repeat work over each item in a list", "Count with range()", "Accumulate a total in a loop"],
            explanation=(
                "for item in collection: runs the indented block once per item. range(n) counts 0 to n-1; range(a, b) counts a to b-1. "
                "An accumulator pattern sets total = 0 before the loop and adds inside it. Off-by-one mistakes usually come from forgetting that the end of range is excluded."
            ),
            examples=[
                Example(code="for n in range(3):\n    print(n)", output="0\n1\n2"),
                Example(code="total = 0\nfor n in range(1, 5):\n    total += n\nprint(total)", output="10", note="1 + 2 + 3 + 4; the 5 is excluded."),
                Example(code="for word in ['tea', 'rice']:\n    print(word.upper(), len(word))", output="TEA 3\nRICE 4"),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Print the sum of the even numbers below 100 (0, 2, 4 ... 98).",
                    checks=[
                        Check(kind="requires_node", value="For", message="Use a for loop."),
                        Check(kind="requires_call", value="range", message="Count with range()."),
                        Check(kind="output_equals", value="2450", message="Expected output: 2450"),
                    ],
                    hints=["range(0, 100, 2) steps by two.", "Alternatively test n % 2 == 0 inside the loop.", "If you get 2550 you included 100: range excludes its end."],
                    topics=["loops", "range", "accumulator"], expected_output="2450",
                ),
                Exercise(
                    id="e2", prompt="Given names = ['Ada', 'Grace', 'Linus'], print each name with its position starting at 1, like '1. Ada'.",
                    starter="names = ['Ada', 'Grace', 'Linus']\n",
                    checks=[
                        Check(kind="requires_node", value="For", message="Loop over the names."),
                        Check(kind="output_equals", value="1. Ada\n2. Grace\n3. Linus", message="Expected three lines: 1. Ada / 2. Grace / 3. Linus"),
                    ],
                    hints=["enumerate(names, start=1) gives (position, name) pairs.", "Or keep a counter and add 1 each time."],
                    topics=["loops", "enumerate"], expected_output="1. Ada\n2. Grace\n3. Linus",
                ),
            ],
            topics=["loops", "range", "accumulator"],
            references=[TUT + "controlflow.html#for-statements", TUT + "controlflow.html#the-range-function"],
        ),
        Lesson(
            id="l5-conditions",
            title="if, elif, else and comparisons",
            objectives=["Branch on conditions", "Combine conditions with and/or/not", "Avoid common comparison mistakes"],
            explanation=(
                "if runs its block when the condition is true; elif tests another condition; else catches the rest. "
                "Comparisons produce True or False; == tests equality (a single = assigns). and requires both sides, or either, not flips. "
                "Empty strings, 0 and empty lists count as false in a condition."
            ),
            examples=[
                Example(code="temp = 17\nif temp < 16:\n    print('cold')\nelif temp < 21:\n    print('fine')\nelse:\n    print('warm')", output="fine"),
                Example(code="items = []\nif not items:\n    print('nothing to buy')", output="nothing to buy"),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Given hour = 19, print 'Good morning' before 12, 'Good afternoon' before 18, otherwise 'Good evening'.",
                    starter="hour = 19\n",
                    checks=[
                        Check(kind="requires_node", value="If", message="Use if/elif/else."),
                        Check(kind="contains_text", value="elif", message="Use elif for the middle case rather than nested ifs."),
                        Check(kind="output_equals", value="Good evening", message="With hour = 19 the output should be: Good evening"),
                    ],
                    hints=["Test the earliest boundary first: hour < 12."],
                    topics=["conditions", "comparisons"], expected_output="Good evening",
                ),
            ],
            topics=["conditions", "booleans"],
            references=[TUT + "controlflow.html#if-statements", "https://docs.python.org/3/library/stdtypes.html#truth-value-testing"],
        ),
        Lesson(
            id="l6-functions",
            title="Functions",
            objectives=["Define a function with parameters", "Return a value instead of printing", "Give parameters default values"],
            explanation=(
                "def name(params): creates a function; the body is indented; return hands a value back to the caller. "
                "A function that prints is harder to reuse than one that returns. Default values make parameters optional. "
                "A docstring (a string as the first line) explains what the function does."
            ),
            examples=[
                Example(code="def area(width, height=1):\n    \"\"\"Area of a rectangle.\"\"\"\n    return width * height\n\nprint(area(3, 4), area(5))", output="12 5"),
                Example(code="def greet(name):\n    return f'Hello, {name}'\n\nmessage = greet('Neku')\nprint(message.upper())", output="HELLO, NEKU"),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Write a function celsius_to_fahrenheit(c) that returns c * 9 / 5 + 32, then print celsius_to_fahrenheit(20).",
                    checks=[
                        Check(kind="defines_function", value="celsius_to_fahrenheit", message="Define celsius_to_fahrenheit."),
                        Check(kind="requires_node", value="Return", message="Return the value rather than printing inside the function."),
                        Check(kind="output_equals", value="68.0", message="Expected output: 68.0"),
                    ],
                    hints=["Division with / gives a float, so 68.0 is right.", "Call the function inside print()."],
                    topics=["functions", "return"], expected_output="68.0",
                ),
            ],
            topics=["functions", "return", "defaults"],
            references=[TUT + "controlflow.html#defining-functions", TUT + "controlflow.html#default-argument-values"],
        ),
        Lesson(
            id="l7-dicts",
            title="Dictionaries",
            objectives=["Store values under keys", "Read with [] and .get()", "Loop over items"],
            explanation=(
                "A dict maps keys to values: prices['tea'] = 3.2. Reading a missing key with [] raises KeyError; .get(key, default) returns the default instead. "
                "for key, value in d.items(): visits each pair. Keys are usually strings or numbers."
            ),
            examples=[
                Example(code="prices = {'tea': 3.2, 'rice': 1.5}\nprices['milk'] = 1.1\nprint(prices['tea'], prices.get('bread', 0))\nfor item, price in prices.items():\n    print(item, price)", output="3.2 0\ntea 3.2\nrice 1.5\nmilk 1.1"),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Count how many times each word appears in words = ['tea', 'rice', 'tea'] and print the dictionary.",
                    starter="words = ['tea', 'rice', 'tea']\n",
                    checks=[
                        Check(kind="requires_node", value="Dict", message="Build a dictionary (start with counts = {})."),
                        Check(kind="requires_node", value="For", message="Loop over the words."),
                        Check(kind="output_equals", value="{'tea': 2, 'rice': 1}", message="Expected output: {'tea': 2, 'rice': 1}"),
                    ],
                    hints=["counts.get(word, 0) + 1 handles the first time a word appears.", "Dictionaries keep insertion order, so tea comes first."],
                    topics=["dicts", "loops"], expected_output="{'tea': 2, 'rice': 1}",
                ),
            ],
            topics=["dicts"],
            references=[TUT + "datastructures.html#dictionaries"],
        ),
        Lesson(
            id="l8-files-errors",
            title="Files and errors",
            objectives=["Read a text file safely with with", "Handle a missing file with try/except", "Understand what an exception is"],
            explanation=(
                "with open(path) as f: opens a file and closes it automatically, even if something goes wrong. f.read() gives the whole text; "
                "looping over f gives lines. If the file does not exist, open raises FileNotFoundError; catching it with try/except lets your program "
                "report the problem instead of crashing. Catch specific exceptions, not a bare except."
            ),
            examples=[
                Example(code="try:\n    with open('/definitely/not/here.txt') as f:\n        print(f.read())\nexcept FileNotFoundError:\n    print('no such file')", output="no such file"),
                Example(code="try:\n    int('twelve')\nexcept ValueError as e:\n    print('bad number:', e)", output="bad number: invalid literal for int() with base 10: 'twelve'"),
            ],
            exercises=[
                Exercise(
                    id="e1", prompt="Write code that tries to open 'notes.txt' and print how many lines it has; if the file is missing print 'notes.txt not found'.",
                    checks=[
                        Check(kind="requires_node", value="With", message="Open the file with a with statement."),
                        Check(kind="requires_node", value="Try", message="Use try/except."),
                        Check(kind="contains_text", value="FileNotFoundError", message="Catch FileNotFoundError specifically, not a bare except."),
                        Check(kind="forbids_node", value="BareExcept", message="Do not use a bare except: it hides every error."),
                    ],
                    hints=["len(f.readlines()) counts lines.", "The except clause names the exception: except FileNotFoundError:"],
                    topics=["files", "exceptions"],
                ),
            ],
            topics=["files", "exceptions"],
            references=[TUT + "inputoutput.html#reading-and-writing-files", TUT + "errors.html#handling-exceptions"],
            next_steps="You can now read the official tutorial's chapters on modules and classes with confidence.",
        ),
    ],
)
