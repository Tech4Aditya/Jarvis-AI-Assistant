#include<bits/stdc++.h>
using namespace std;
class Base {};
class derived: public Base {};
int main() {

    derived d;
    try {
        throw d;
    }
    catch (Base b) {
        cout<<"Base";
    }
    catch (derived d) {
        cout<<"derived";
    }
    return 0;
}