#include <stdio.h>
#include <stdlib.h>
#include <time.h>

void print_random_words(void) {
    const char *words[] = {"the", "quick", "brown", "fox", "jumps", "over",
"over", "lazy", "dog", "a", "very", "random", "sequence"};
    int num_words = sizeof(words) / sizeof(words[0]);
    
    srand(time(NULL));
    
    for (int i = 0; i < 4; i++) {
        int index = rand() % num_words;
        printf("%s", words[index]);
        if (i < 3) {
            printf(" ");
        }
    }
    printf("\n");
}

int main(void) {
    print_random_words();
    return 0;
}

