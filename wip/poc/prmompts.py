keywords_topics_example = {
    "field_of_study": ["Political Science", "Social Media Studies", "Communication Studies", "Sociology, Digital Culture"],
    "keywords_and_topics": ["social media usage", "political polarization", "mixed-methods approach", "semi-structured interviews"],
    "tags": ["online behavior", "echo chambers", "survey methodology", "young adults", "political communication", "digital ethnography", "ideology"],
}

keywords_topics_prompt = """You are a sophisticated academic scholar with expertise in {domain}. 
You are renowned for your ability to quickly grasp the core concepts of research papers and expertly categorize and tag information for optimal organization and retrieval.

## TASK
When presented with title and abstraction of a research paper, you will meticulously analyze its content and provide the following:
- field_of_study: Propose 2-4 detailed academic categories that this research paragraph would logically fall under. These categories should help situate the research within the fields of study. Consider the interdisciplinary nature of the paragraph as well.
- keywords_and_topics: Identify 3-5 key terms or phrases that accurately capture the specific subject matter and central ideas discussed within the paragraph. These keywords should be highly relevant and commonly used within the specific research area.
- tags: Suggest 3-5 concise tags that could be used to further refine the indexing and searchability of the paragraph. These tags might include specific methodologies, theories, named entities, or emerging concepts mentioned within the text. They should be specific enough to differentiate the content from the broader categories.

Make sure you output in json with double quotes.

## EXAMPLE
Here is an example for demonstraction purpose only. Do not use this specific example in your response, it is solely illustrative.

Input Paragraph:  
<title>  Social media usage heighten political polarization in youth - A quantitative study</title>
<abstract>
"This study employed a mixed-methods approach to investigate the impact of social media usage on political polarization among young adults in urban areas. 
Quantitative data was collected through a survey of 500 participants, while qualitative data was gathered via semi-structured interviews with a subset of 25 participants. 
The findings suggest a correlation between increased exposure to ideologically homogeneous content online and heightened political polarization."
</abstract>

Hypothetical Output from this Example (Again, illustrative and not to be used in the actual response):
```json
{example_json}
```

## INSTRUCTIONS
1. Your response should be clearly organized, using bullet points or numbered lists to separate the categories, keywords, and tags.
2. Be precikeywords_topics_promptse and avoid overly broad or generic terms.
3. Prioritize terms that are commonly used within the relevant academic field.
4. Focus on accurate representation of the content provided.
5. Ensure that categories, keywords, and tags are directly relevant to the specific area of expertise you are embodying.
6. Please analyze the following paragraph and provide your expert recommendations:

## INPUT
Now start analyzing the following paper.
<title> {title} </title>
<abstract>
{abstract}
</abstract>

## OUTPUT

"""

keywords_topics_prompt_2 = """Try your very best to extract keywords or topics based on title and abstract from the following research paper.
Make sure these keywords or topics are highly representative and distinguishable.

title:'HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models'
abstract:'In order to thrive in hostile and ever-changing natural environments, mammalian brains evolved to store large amounts of knowledge about the world and continually integrate new information while avoiding catastrophic forgetting. Despite the impressive accomplishments, large language models (LLMs), even with retrieval-augmented generation (RAG), still struggle to efficiently and effectively integrate a large amount of new experiences after pre-training. In this work, we introduce HippoRAG, a novel retrieval framework inspired by the hippocampal indexing theory of human long-term memory to enable deeper and more efficient knowledge integration over new experiences. HippoRAG synergistically orchestrates LLMs, knowledge graphs, and the Personalized PageRank algorithm to mimic the different roles of neocortex and hippocampus in human memory. We compare HippoRAG with existing RAG methods on multi-hop question answering and show that our method outperforms the state-of-the-art methods remarkably, by up to 20%. Single-step retrieval with HippoRAG achieves comparable or better performance than iterative retrieval like IRCoT while being 10-30 times cheaper and 6-13 times faster, and integrating HippoRAG into IRCoT brings further substantial gains. Finally, we show that our method can tackle new types of scenarios that are out of reach of existing methods. Code and data are available at https://github.com/OSU-NLP-Group/HippoRAG.'

Please output in list format.
"""


search_query_prompt = """You are a sophisticated academic scholar and an expert with search engine. 
Given the following paper related information, could you utilize your knowledge and skills to compose 2-4 search queries?
These search queries would be used in Google Scholar to find more related works and literatures.

## INPUT
Now start analyzing the following paper.
<title> {title} </title>

<abstract>
{abstract}
</abstract>

<keywords> {keywords} </keywords>

<tags> {tags} </tags>

<fields> {field_of_study} </fields>

## OUTPUT
Output your search queries in list format. Do not include anything else.

"""
