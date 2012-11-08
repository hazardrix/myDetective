'''
Created on 27.09.2012

@author: Peter
'''
import operator
import itertools
print "loading libraries...",
import sys, nltk, os, Data, string, re, math, collections, urllib2
from fwords import fwords
from database import database #@UnresolvedImport
from decimal import *
from corpusstatistics import corpusstatistics
from nltk.corpus import LazyCorpusLoader
from nltk.corpus.reader import *
from nltk.tag import *
from nltk.collocations import *
from subprocess import *
from nltk.corpus import wordnet as wn
print "- done"

f = False
t = True
settings = {'FunctionWordFrequency' : f, 
            'BigramFrequency' : f, 
            'TrigramFrequency' : f, 
            'AverageWordLength' : f, 
            'AverageSentenceLength' : f, 
            'LexicalDiversity' : f,
            'spellingMistakes' : f,
            'punctuation' : f,
            'PartOfSpeech' : f}

#don't change this
bigramIndices = []
trigramIndices = []
bi_filter =  0
tri_filter = 0
spell_filter = 0
test_method_bi  = [None,None]
test_method_tri = [None,None]
x = nltk.collocations.BigramAssocMeasures()
bi_meassures = {"Raw frequency":x.raw_freq, "Chi-squared":x.chi_sq, "Dice's coefficient":x.dice, "Jaccard Index":x.jaccard, "Likelihood-ratio":x.likelihood_ratio, "Mutual Information":x.mi_like, "Phi coefficient":x.phi_sq, "Pointwise mutual information":x.pmi, "Poisson-stirling":x.poisson_stirling, "Student's-t":x.student_t}
x = nltk.collocations.TrigramAssocMeasures()
tri_meassures = {"Raw frequency":x.raw_freq, "Chi-squared":x.chi_sq, "Jaccard Index":x.jaccard, "Likelihood-ratio":x.likelihood_ratio, "Mutual Information":x.mi_like, "Pointwise mutual information":x.pmi, "Poisson-stirling":x.poisson_stirling, "Student's-t":x.student_t}
training_mode = True
db = database()
opener = urllib2.build_opener()
opener.addheaders = [('User-agent', 'Mozilla/5.0')]
word_list = []
spellVector = []

#Sequence of part of speech pairs is saved here
pos_trans = []

#cache for batch - if same feature several times calculated, this will be used to save cpu time
feature_cache = {}
enable_caching = t
##################

def partOfSpeechVector(sentences):
    global pos_trans, bi_filter
    tagged = nltk.batch_pos_tag(sentences)
    
    tags = []
    for sentence in tagged:
        td = [w[1] for w in sentence]
        td.append("EOS") #add end of sentence "tag"
        td.reverse()
        td.append("SOS") #add start of sentence "tag"
        td.reverse()
        for t in td:
            if all(c in string.letters for c in t):
                tags.append(t)
                
    x =  BigramFrequencyToUnifiedVector(BigramFrequency(tags, bi_meassures["Raw frequency"], True))
    return x

def spellingVector(words):
    global spellVector, spell_filter
    tokens = [w for w in words if isMissSpelled(w)]
    types = set(tokens)
    filtered = []
    
    #Only consider words that appear for at least a certain threshold value spell_filter
    for typ in types:
        if tokens.count(typ) >= spell_filter:
            filtered.append(typ)

    spelling_mistakes = []
    
    for spell in spellVector:
        if spell in filtered:
            spelling_mistakes.append(1)
        else:
            spelling_mistakes.append(0)
    
    for typ in filtered:
        spelling_mistakes.append(1)
        spellVector.append(typ)
    
    return spelling_mistakes
    

def getWikipediaInformation(word):
    inf = db.getSpelling(word)
    if inf == None:
        try:
            page = opener.open("http://en.wikipedia.org/w/api.php?action=query&format=xml&list=search&srsearch=" + word + "&srprop=timestamp").read()
            r1 = re.compile(r"totalhits=\"(.*?)\"")
            r2 = re.compile(r"suggestion=\"(.*?)\"")
            m = [r1.search(page), r2.search(page)]
            if m[0]:
                if m[1]:
                    distance = nltk.distance.edit_distance(word, m[1].group(1))
                    db.saveSpelling(word, m[0].group(1), m[1].group(1), distance)
                else:
                    db.saveSpelling(word, m[0].group(1))
            else:
                return None
        except:
            return None
    else:
        return inf


def missSpelledFunctionWord(word):
    #adaptive word distance limit depending on length of word
    if (len(word) > 1 and 
        len(set(word) & set(string.letters)) > 0 and 
        wn.morphy(word) == None and                     #@UndefinedVariable
        len(wn.synsets(word)) == 0 and                  #@UndefinedVariable
        not fwords.isFunctionWord(word)):
        
            lim = math.ceil(math.log(len(word))) - 1 #@UndefinedVariable
            if len(word) > 4:
                if distToFuncWords(word) <= lim:
                    return True
            return False
    else:
        return False
        

def isMissSpelled(word):
        try:
            if (len(word) > 1 and 
                len(set(word) & set(string.letters)) > 0 and 
                wn.morphy(word) == None and                     #@UndefinedVariable
                len(wn.synsets(word)) == 0 and                  #@UndefinedVariable
                not fwords.isFunctionWord(word) and
                len(word.split("-")) == 1):
                
                word_data = getWikipediaInformation(word)
                if word_data == None:
                    return False
                hits = int(word_data[1])
                suggestion = word_data[2]
                distance = int(word_data[3])

                if suggestion != "":
                    return True
                else:
                    if distToFuncWords(word) < 3:
                        return True
                    else:
#                        if hits < 10:
#                            return True
#                        else:
                        return False
                        
                        
#                if hits == 0:
#                    if suggestion != "":
#                        #assume no spelling error - probably some proper name which is not very common
#                        return False
                
#                if hits < 10:
#                    if suggestion != "":
#                        if distance < 4:
#                            return True
#                        else:
#                            return False
#                    else:
#                        if distToFuncWords(word) < 3:
#                            return True
#                        else:
#                            return False
#                else:
#                    return False
                    
            else:
                return False
        except:
            return False

def distToFuncWords(word):
    '''returns a words smallest levenshtein distance to words in a set of function words'''
    return min([nltk.distance.edit_distance(word, fw) for fw in fwords().getWords()])

def main(args):
    global training_mode, test_method_bi, test_method_tri
    #db.initWikipediaCache()
    
    
    
    batchTest()
    #mostWritten()
#    train = "training.lsvm"
#    test = "testing.lsvm"
#    cross_test = "cross.lsvm"
#    print "started..."
#    for mes in bi_meassures:
#        training_mode = True
#        test_method_bi[0] = mes
#        test_method_bi[1] = bi_meassures[mes]
#        #training(train)
#        #testing(test)
#        #svm(train, test)
#        training(cross_test)
#        svm(cross_test)
        
def batchTest():
    '''This function tests all possible combinations of features using cross validation'''
    global t, f, bi_filter, tri_filter, spell_filter, settings, test_method_bi, test_method_tri
    output = "cross.lsvm"
    authors = getAuthors('../crosstesting/')
    
    print "\n--------------------------------------------------------------------------------"
    print "--Batch Testing of all possible combinations of features with cross validation--"
    print "--This test can take many hours - depending on your CPU and number of documents-"
    print "--------------------------------------------------------------------------------\n"
    print "Testing with: " + str(len(authors)) + " authors and a total of " + str(sum([len(authors[x]) for x in authors])) + " documents\n\n"
    
#    bi_filter = 2
#    cset(f,f,f,f,f,f,f,f,t)
#    
#    crosstesting(output)
    
    #using best results from previous test runs
#    bi_filter =  -1
#    tri_filter = 1
#    test_method_bi  = ["Raw frequency", bi_meassures["Raw frequency"]]
#    test_method_tri = ["Pointwise mutual information",tri_meassures["Pointwise mutual information"]]
    
#    used = []
#    for key in settings.keys():
#        combine = []
#        combine.append(key)
#        used.append(key)
#        for key2 in [k for k in settings.keys() if used.count(k) == 0]:
#            cset()
#            settings[key] = t
#            settings[key2] = t
#            print key + " - " + key2
#            crosstesting(output)
    
    
#    for i in range(3, len(settings.keys()) + 1):
#        print "combinations of " + str(i) + " features:"
#        for x in itertools.combinations(settings.keys(), i):
#            print " - ".join(x) + ":"
#            cset()
#            for key in x:
#                settings[key] = t
#            crosstesting(output)
    
#    print "spelling errors:"
#    cset(f,f,f,f,f,f,t)
#    for i in range(1, 5):
#        print str(i) + ":"
#        spell_filter = i
#        crosstesting(output)
    
#    print "1) Single Feature Statistics:"
#    print "   [a] Average Word Length:"
#    cset(f,f,f,t)
#    crosstesting(output)
#    
#    print "   [b] Average Sentence Length:"
#    cset(f,f,f,f,t)
#    crosstesting(output)
#      
#    print "   [c] Lexical Diversity:"
#    cset(f,f,f,f,f,t)
#    crosstesting(output)
    
#    print "   [d] Function Word Bigram Frequency using different association measures and frequency filters:"
#    cset(f,t)
#    for mes in bi_meassures:
#        for i in range(1, 5):
#            bi_filter = i
#            test_method_bi[0] = mes
#            test_method_bi[1] = bi_meassures[mes]
#            print "       " + mes + " with frequency filter = " + str(i) + ":"
#            crosstesting(output)
#        bi_filter = -1 # this tells the function to use adaptive one
#        test_method_bi[0] = mes
#        test_method_bi[1] = bi_meassures[mes]
#        print "       " + mes + " with adaptive frequency filter based on text length:"
#        crosstesting(output)
        
#    print "   [d] Function Word Trigram Frequency using different association measures and frequency filters:"
#    cset(f,f,t)
#    for mes in tri_meassures:
#        for i in range(1, 5):
#            tri_filter = i
#            test_method_tri[0] = mes
#            test_method_tri[1] = tri_meassures[mes]
#            print "       " + mes + " with frequency filter = " + str(i) + ":"
#            crosstesting(output)
#        tri_filter = -1 # this tells the function to use adaptive one
#        test_method_tri[0] = mes
#        test_method_tri[1] = tri_meassures[mes]
#        print "       " + mes + " with adaptive frequency filter based on text length:"
#        crosstesting(output)
        
    print "   [f] Function Word Frequency:"
    cset(t)
    crosstesting(output)
#    
#    print "Combined Feature Statistics:"

def cset(FunctionWordFrequency = False, BigramFrequency = False, 
         TrigramFrequency = False, AverageWordLength = False, 
         AverageSentenceLength = False, LexicalDiversity = False, 
         spellingMistakes = False, punctuation = False,
         partOfSpeech = False):
    '''change settings'''
    global settings
    settings['FunctionWordFrequency'] = FunctionWordFrequency
    settings['BigramFrequency'] = BigramFrequency
    settings['TrigramFrequency'] = TrigramFrequency
    settings['AverageWordLength'] = AverageWordLength
    settings['AverageSentenceLength'] = AverageSentenceLength
    settings['LexicalDiversity'] = LexicalDiversity
    settings['spellingMistakes'] = spellingMistakes
    settings['punctuation'] = punctuation
    settings['PartOfSpeech'] = partOfSpeech

def crosstesting(filen):
    processAuthorFolder('../crosstesting/', filen)
    svm(filen)
    
def training(filen):
    processAuthorFolder('../training/', filen)
    svm(filen)

def testing(filen):
    global training_mode
    training_mode = False
    processAuthorFolder('../testing/', filen)
    svm(filen)

def svm(train, test = None):
    if (test != None):
        cmd = './svmtools/easy.py "{0}" "{1}"'.format(train, test)
        output = Popen(cmd, shell = True, stdout = PIPE, stderr = None)
        text = output.stdout.read()
        print text
#        r = re.compile('Accuracy\s=\s(.*?)\s\(classification\)')
#        m = r.search(text)
#        if m:
#            print test_method_bi[0] + ": " + m.group(1)
    else:
        cmd = './svmtools/easy.py "{0}"'.format(train)
        output = Popen(cmd, shell = True, stdout = PIPE, stderr = None)
        text = output.stdout.read()
        print text
#        r = re.compile(r'CV\srate=(.*?)\n')
#        m = r.search(text)
#        if m:
#            print "------> " + m.group(1) + "%"

def testDocument():
    pass

def processAuthorFolder(input_folder, output_file):
    wfile = open(output_file, "w");
    
    authors = getAuthors(input_folder)
    author_id = 0
    for author in authors:
        author_id += 1
        for file_ in authors[author]:
            wfile.write(listToSVMVector(author_id, getAttributeVector(file_[1])))
    wfile.close()
    
def getAuthors(path = '../training/'):
    """returns a list of authors with corresponding files."""
    authors = collections.OrderedDict()
    author_listing = os.listdir(path)
    for author in author_listing:
        if os.path.isdir(path + author):
            author_path = os.path.join(path, author) + "/"
            file_listing = os.listdir(author_path)
            file_listing = [[file_, author_path + file_] for file_ in file_listing]
            if len(file_listing) > 0:
                authors.update({author:file_listing})
    return authors
    
def getAttributeVector(file_name):
    global bigramIndices, training_mode, settings, feature_cache, enable_caching
    text = Data.Data(file_name).text.lower()
    sentences = nltk.sent_tokenize(text)
    #words = [x for x in nltk.word_tokenize(text) if x not in string.punctuation and re.search("[0-9]", x) == None and x != "``" and x != "''"]
    pattern = re.compile('[\.\'\/]+')
    words = [pattern.sub('', x) for x in nltk.word_tokenize(text) if x not in string.punctuation and re.search("[0-9]", x) == None and x != "``" and x != "''"]
    
    #punctuation
    if settings['punctuation']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('punctuation'):
                punctuation = feature_cache[file_name]['punctuation']
            else:
                punctuation = punctuationVector(text) 
                feature_cache[file_name].update({'punctuation' : punctuation})
        else:
            punctuation = punctuationVector(text) 
            feature_cache.update({file_name:{'punctuation' : punctuation}})
    else: 
        punctuation = []
    
    #part of speech
    
    #spelling mistakes
    if settings['spellingMistakes']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('spellingMistakes'):
                spelling = feature_cache[file_name]['spellingMistakes']
            else:
                spelling = spellingVector(words)
                feature_cache[file_name].update({'spellingMistakes' : spelling})
        else:
            spelling = spellingVector(words)
            feature_cache.update({file_name:{'spellingMistakes' : spelling}})
    else: 
        spelling = []
    
    #lexical diversity
    if settings['LexicalDiversity']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('LexicalDiversity'):
                diversity = feature_cache[file_name]['LexicalDiversity']
            else:
                diversity = [len(words) / len(set(words))]
                feature_cache[file_name].update({'LexicalDiversity' : diversity})
        else:
            diversity = [len(words) / len(set(words))]
            feature_cache.update({file_name:{'LexicalDiversity' : diversity}})
    else: 
        diversity = []

    #function word frequency
    if settings['FunctionWordFrequency']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('FunctionWordFrequency'):
                fword_frequency = feature_cache[file_name]['FunctionWordFrequency']
            else:
                fwords = fwordFrequency(words, len(words))
                fword_frequency = [fwords[f] for f in fwords]
                feature_cache[file_name].update({'FunctionWordFrequency' : fword_frequency})
        else:
            fwords = fwordFrequency(words, len(words))
            fword_frequency = [fwords[f] for f in fwords]
            feature_cache.update({file_name:{'FunctionWordFrequency' : fword_frequency}})
    else: 
        fword_frequency = []
    
    #average word length
    if settings['AverageWordLength']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('AverageWordLength'):
                avg_word = feature_cache[file_name]['AverageWordLength']
            else:
                avg_word = [average_word_length(words)]
                feature_cache[file_name].update({'AverageWordLength' : avg_word})
        else:
            avg_word = [average_word_length(words)]
            feature_cache.update({file_name:{'AverageWordLength' : avg_word}})
    else: 
        avg_word = []
    
    #average sentence length
    if settings['AverageSentenceLength']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('AverageSentenceLength'):
                avg_sent = feature_cache[file_name]['AverageSentenceLength']
            else:
                avg_sent = [average_sentence_length(sentences)]
                feature_cache[file_name].update({'AverageSentenceLength' : avg_sent})
        else:
            avg_sent = [average_sentence_length(sentences)]
            feature_cache.update({file_name:{'AverageSentenceLength' : avg_sent}})
    else: 
        avg_sent = []
    
    #Function Word Bigram Frequency
    if settings['BigramFrequency']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('BigramFrequency'):
                bigram_frequency = feature_cache[file_name]['BigramFrequency']
            else:
                bigram_frequency = BigramFrequencyToUnifiedVector(BigramFrequency(words, test_method_bi[1]))
                feature_cache[file_name].update({'BigramFrequency' : bigram_frequency})
        else:
            bigram_frequency = BigramFrequencyToUnifiedVector(BigramFrequency(words, test_method_bi[1]))
            feature_cache.update({file_name:{'BigramFrequency' : bigram_frequency}})
    else: 
        bigram_frequency = []
    
    #Trigram frequencies
    if settings['TrigramFrequency']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('TrigramFrequency'):
                trigram_frequency = feature_cache[file_name]['TrigramFrequency']
            else:
                trigram_frequency = TrigramFrequencyToUnifiedVector(TrigramFrequency(words, test_method_tri[1]))
                feature_cache[file_name].update({'TrigramFrequency' : trigram_frequency})
        else:
            trigram_frequency = TrigramFrequencyToUnifiedVector(TrigramFrequency(words, test_method_tri[1]))
            feature_cache.update({file_name:{'TrigramFrequency' : trigram_frequency}})
    else: 
        trigram_frequency = []
    
    #PartOfSpeech
    if settings['PartOfSpeech']:
        if enable_caching and feature_cache.has_key(file_name):
            if feature_cache[file_name].has_key('PartOfSpeech'):
                part_of_speech = feature_cache[file_name]['PartOfSpeech']
            else:
                part_of_speech = partOfSpeechVector([nltk.word_tokenize(snt) for snt in sentences])
                feature_cache[file_name].update({'PartOfSpeech' : part_of_speech})
        else:
            part_of_speech = partOfSpeechVector([nltk.word_tokenize(snt) for snt in sentences])
            feature_cache.update({file_name:{'PartOfSpeech' : part_of_speech}})
    else: 
        part_of_speech = []
    
    return diversity + fword_frequency + avg_word + avg_sent + bigram_frequency + trigram_frequency + spelling + part_of_speech

def bigramsToStringVector(bigrams):
    return {b[0][0] + "_" + b[0][1] : b[1] for b in bigrams}

def trigramsToStringVector(bigrams):
    return {b[0][0] + "_" + b[0][1] + "_" + b[0][2] : b[1] for b in bigrams}

def listToSVMVector(ida, listl):
    """ Transforms dictionary to libsvm readable date """
    out = str(ida)
    for idx, val in enumerate(listl):
        if str(val) != "0": 
            out += " " + str(idx) + ":" + str(val)
    #print out
    out += "\n"
    return out
    
def prepare_ngrams(ngrams):
    """ Prepares the list of n-grams, he or she -> it and so on.
        Input: two-dimensional list of n-grams"""
    for index_ngram, ngram in enumerate(ngrams):
        for index_word, word in enumerate(ngram):
            if word in ["he", "she"]: ngrams[index_ngram][index_word]="it"
            if word in ["his", "hers"]: ngrams[index_ngram][index_word]="its"
    return ngrams

def average_word_length(words):
    """ Calculates the average length of a word in array.
        Will reject all non-words with regular expression."""
    words_total = 0
    length_total = 0
    for word in words:
        if re.match("^[A-Za-z-/]+.?$", word):
            length_total += len(word)
            words_total += 1
    return length_total/float(words_total)

def average_sentence_length(sentences):
    """ Calculates the average length (in words) of a sentence in array."""
    length_total = 0
    for sentence in sentences:
        length_total += len(nltk.word_tokenize(sentence))
    return length_total/float(len(sentences))
    
def fwordFrequency(words, token_count):
    text_fwords = fwords()
    return text_fwords.relativeFrequencyWordArray(words, token_count)

def BigramFrequency(words, test_method, pos = False):
    global bi_filter
    return_array = []
    finder = BigramCollocationFinder.from_words(words)
    if bi_filter != -1:
        finder.apply_freq_filter(bi_filter)
    else:
        finder.apply_freq_filter(math.ceil(math.log(len(words) - 1) /3) - 1) #@UndefinedVariable
    scored = finder.score_ngrams(test_method)
    for score in scored:
        if(fwords.isFunctionWord(score[0][0]) and fwords.isFunctionWord(score[0][1])) or pos:
            return_array.append(score)
    return return_array

def BigramFrequencyToUnifiedVector(bg_freq):
    global bigramIndices, training_mode
    bigram_frequency = bigramsToStringVector(bg_freq)
    bigram_vector = []    
    for bigram in bigramIndices:
        if bigram in bigram_frequency.keys():
            bigram_vector.append([bigram,bigram_frequency[bigram]])
            if bigramIndices.index(bigram) != bigram_vector.index([bigram,bigram_frequency[bigram]]):
                print "FAILURE: " + str(bigramIndices.index(bigram)) + " != " + str(bigram_vector.index(bigram))
                sys.exit()
            del bigram_frequency[bigram]
        else:
            bigram_vector.append([bigram,0])
            if bigramIndices.index(bigram) != bigram_vector.index([bigram,0]):
                print "FAILURE: " + str(bigramIndices.index(bigram)) + " != " + str(bigram_vector.index(bigram))
                sys.exit()
    for bigram in bigram_frequency:
        if bigram in bigramIndices:
            print "FAILURE: " + bigram + " should have been removed!"
            sys.exit()
        else:
            if training_mode:
                bigramIndices.append(bigram)
                bigram_vector.append([bigram,bigram_frequency[bigram]])
            else:
                pass
    return [b[1] for b in bigram_vector]
    
def TrigramFrequency(words, test_method, pos = False):
    global tri_filter
    return_array = []
    finder = TrigramCollocationFinder.from_words(words)
    if tri_filter != -1:
        finder.apply_freq_filter(tri_filter)
    else:
        finder.apply_freq_filter(math.ceil(math.log(len(words) - 1) /3) - 1) #@UndefinedVariable
    scored = finder.score_ngrams(test_method)
    for score in scored:
        if(not pos and fwords.isFunctionWord(score[0][0]) and fwords.isFunctionWord(score[0][1]) and fwords.isFunctionWord(score[0][2])):
            return_array.append(score)
    return return_array

def TrigramFrequencyToUnifiedVector(bg_freq):
    global trigramIndices, training_mode
    trigram_frequency = trigramsToStringVector(bg_freq)
    trigram_vector = []    
    for trigram in trigramIndices:
        if trigram in trigram_frequency.keys():
            trigram_vector.append([trigram,trigram_frequency[trigram]])
            if trigramIndices.index(trigram) != trigram_vector.index([trigram,trigram_frequency[trigram]]):
                print "FAILURE: " + str(trigramIndices.index(trigram)) + " != " + str(trigram_vector.index(trigram))
                sys.exit()
            del trigram_frequency[trigram]
        else:
            trigram_vector.append([trigram,0])
            if trigramIndices.index(trigram) != trigram_vector.index([trigram,0]):
                print "FAILURE: " + str(trigramIndices.index(trigram)) + " != " + str(trigram_vector.index(trigram))
                sys.exit()
    for trigram in trigram_frequency:
        if trigram in trigramIndices:
            print "FAILURE: " + trigram + " should have been removed!"
            sys.exit()
        else:
            if training_mode:
                trigramIndices.append(trigram)
                trigram_vector.append([trigram,trigram_frequency[trigram]])
            else:
                pass
    return [b[1] for b in trigram_vector]  

def punctuationVector(text):
    '''returns a vector with punctuation statistics from a text'''
    size = len(text)
    return [Decimal(text.count(".")) / Decimal(size), 
            Decimal(text.count(",")) / Decimal(size), 
            Decimal(text.count("?")) / Decimal(size), 
            Decimal(text.count("!")) / Decimal(size), 
            Decimal(text.count(":")) / Decimal(size), 
            Decimal(text.count(";")) / Decimal(size),
            Decimal(text.count("-")) / Decimal(size)]
    pass


#just a helper function for finding the students with the most text data
def mostWritten():
    authors = {}
    files = os.listdir("../CORPUS_TXT/")
    for filed in files:
        if filed[len(filed)-3:len(filed)] == "txt" and "Freq" not in filed:
            size = os.path.getsize("../CORPUS_TXT/" + filed)
            author = filed[0:len(filed)-5]
            if author in authors:
                authors[author][0] = authors[author][0] + size
                authors[author][1] = authors[author][1] + 1
            else:
                authors.update({author:[size, 1]})
                
    authors2 = sorted(authors.items(), key=operator.itemgetter(1), reverse=True)
    print authors2
    authors = sorted(authors.items(), key=lambda (k, v): operator.itemgetter(1)(v), reverse=True)
    print authors

if __name__ == '__main__':
    main(sys.exit(main(sys.argv)))    
    
def corpusStuff(init = False):
    #change this for loading another training corpus:
    corpus = LazyCorpusLoader('brown', CategorizedTaggedCorpusReader, 
                              r'c[a-z]\d\d', cat_file='cats.txt', 
                              tag_mapping_function=simplify_brown_tag)
    
    #change this for using a different test method.
    test_method_bi  = nltk.collocations.BigramAssocMeasures().pmi
    test_method_tri = nltk.collocations.TrigramAssocMeasures().pmi
    corpus_stats = corpusstatistics(corpus)
    corpus_fword_frequency = corpus_stats.getRelativeFunctionWordFrequency()
    corpus_bigram_frequency = corpus_stats.getBigramFrequency(test_method_bi)
    
main()
